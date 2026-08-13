"""
bot.py
Alpaca PAPER TRADING hesabinda, gunluk teknik sinyale gore otomatik alim/satim yapan bot.

ONEMLI:
- Bu bot yatirim tavsiyesi vermez, finansal danisman degildir.
- Gostergeler GUNLUK veriye dayanir -> gunde 1 kez, piyasa kapanisina yakin calistirilmalidir.
- Bu script sadece PAPER (sanal) hesaba baglanir (paper=True).
- Birkac haftalik sonuca bakip strateji hakkinda kesin yargida bulunmak istatistiksel
  olarak yaniltici olabilir - kisa vadeli gurultu ile gercek performansi ayirt etmek
  onemli sayida islem/gun gerektirir.
"""

import logging
import math
from datetime import datetime, timedelta

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

import config
from strategy import build_signal
from screener import scan_universe, pick_buy_candidates
from universe import UNIVERSE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("bot_log.txt", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("signal-bot")


def get_price_history(data_client: StockHistoricalDataClient, ticker: str) -> pd.DataFrame:
    start = datetime.now() - timedelta(days=config.LOOKBACK_DAYS)
    request = StockBarsRequest(
        symbol_or_symbols=[ticker],
        timeframe=TimeFrame.Day,
        start=start,
        feed=DataFeed.IEX,  # ucretsiz veri kaynagi (SIP icin ucretli abonelik gerekir)
    )
    bars = data_client.get_stock_bars(request)
    df = bars.df.reset_index()
    df = df[df["symbol"] == ticker].sort_values("timestamp")
    return df[["timestamp", "close", "high", "low"]].reset_index(drop=True)


def get_open_qty(trading_client: TradingClient, ticker: str) -> float:
    try:
        pos = trading_client.get_open_position(ticker)
        return float(pos.qty)
    except Exception:
        return 0.0


def compute_stop_take(price: float, atr_val):
    """ATR varsa ATR bazli, yoksa sabit yuzde bazli stop/hedef doner."""
    if config.USE_ATR_STOPS and atr_val is not None and atr_val > 0:
        stop_price = price - config.ATR_STOP_MULT * atr_val
        take_price = price + config.ATR_TARGET_MULT * atr_val
        method = f"ATR bazli (ATR={atr_val:.2f})"
    else:
        stop_price = price * (1 - config.STOP_LOSS_PCT / 100)
        take_price = price * (1 + config.TAKE_PROFIT_PCT / 100)
        method = "sabit yuzde bazli"
    return round(max(stop_price, 0.01), 2), round(take_price, 2), method


def place_buy(trading_client: TradingClient, ticker: str, price: float, atr_val=None):
    qty = math.floor(config.ALLOCATION_PER_TRADE_USD / price)
    if qty < 1:
        log.info(f"[{ticker}] Ayrilan tutar ({config.ALLOCATION_PER_TRADE_USD} USD) 1 adet almaya yetmiyor, atlaniyor.")
        return

    stop_price, take_price, method = compute_stop_take(price, atr_val)

    if config.DRY_RUN:
        log.info(f"[{ticker}] DRY_RUN: {qty} adet ALIM yapilirdi @ ~{price:.2f} "
                  f"(stop {stop_price} / hedef {take_price}, {method})")
        return

    order = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=take_price),
        stop_loss=StopLossRequest(stop_price=stop_price),
    )
    trading_client.submit_order(order)
    log.info(f"[{ticker}] ALIM emri gonderildi: {qty} adet @ piyasa (stop {stop_price} / hedef {take_price}, {method})")


def place_sell(trading_client: TradingClient, ticker: str):
    if config.DRY_RUN:
        log.info(f"[{ticker}] DRY_RUN: mevcut pozisyon KAPATILIRDI (SAT).")
        return
    trading_client.close_position(ticker)
    log.info(f"[{ticker}] Pozisyon kapatildi (SAT).")


def run_once():
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.error("ALPACA_API_KEY / ALPACA_SECRET_KEY tanimli degil. .env dosyani kontrol et.")
        return

    trading_client = TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)
    data_client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)

    account = trading_client.get_account()
    log.info(f"Hesap durumu: bakiye(cash)={account.cash} | portfoy degeri={account.portfolio_value} | "
             f"DRY_RUN={config.DRY_RUN} | AUTO_SELECT={config.AUTO_SELECT} | "
             f"TREND_FILTER={config.TREND_FILTER_ENABLED} | ATR_STOPS={config.USE_ATR_STOPS}")

    open_positions = trading_client.get_all_positions()
    held_tickers = {p.symbol for p in open_positions}

    # --- 1) ELDE OLAN pozisyonlari her zaman kontrol et (satis karari icin) ---
    for ticker in held_tickers:
        try:
            df = get_price_history(data_client, ticker)
            if len(df) < 20:
                log.warning(f"[{ticker}] Yetersiz veri, satis kontrolu atlandi.")
                continue
            signal = build_signal(df, config.TREND_FILTER_ENABLED)
            qty_held = get_open_qty(trading_client, ticker)
            log.info(
                f"[{ticker}] (ELDE VAR) skor={signal['composite']} verdict={signal['verdict']} "
                f"trend={signal['trend_state']} son_fiyat={signal['last_close']:.2f} pozisyon={qty_held} | "
                f"{signal['details']}"
            )
            if signal["composite"] <= config.SELL_SCORE_THRESHOLD:
                place_sell(trading_client, ticker)
        except Exception as e:
            log.exception(f"[{ticker}] Hata (elde olan pozisyon kontrolu): {e}")

    # --- 2) YENI ALIM adaylarini belirle ---
    slots_available = config.MAX_OPEN_POSITIONS - len(held_tickers)
    if slots_available <= 0:
        log.info(f"MAX_OPEN_POSITIONS ({config.MAX_OPEN_POSITIONS}) doldu, yeni alim yapilmayacak.")
        return

    if config.AUTO_SELECT:
        log.info(f"AUTO_SELECT aktif: {len(UNIVERSE)} hisse taraniyor "
                 f"(BUY_SCORE_THRESHOLD={config.BUY_SCORE_THRESHOLD}, MAX_STOCK_PRICE={config.MAX_STOCK_PRICE})...")
        scan_results = scan_universe(get_price_history, data_client, UNIVERSE, config.TREND_FILTER_ENABLED)
        top_n = min(config.TOP_N, slots_available)
        candidates = pick_buy_candidates(
            scan_results, top_n, held_tickers, config.BUY_SCORE_THRESHOLD, config.MAX_STOCK_PRICE
        )

        for r in scan_results[:10]:
            s = r["signal"]
            log.info(f"[TARAMA] {r['ticker']}: skor={s['composite']} verdict={s['verdict']} "
                     f"trend={s['trend_state']} fiyat={s['last_close']:.2f}")

        if not candidates:
            log.info("AUTO_SELECT: kosullari saglayan (skor+fiyat filtresi) hisse bulunamadi.")
        for c in candidates:
            ticker = c["ticker"]
            signal = c["signal"]
            log.info(f"[{ticker}] (SECILDI) skor={signal['composite']} verdict={signal['verdict']} "
                     f"trend={signal['trend_state']} son_fiyat={signal['last_close']:.2f} | {signal['details']}")
            place_buy(trading_client, ticker, signal["last_close"], signal.get("atr"))
    else:
        for ticker in config.TICKERS:
            if ticker in held_tickers:
                continue
            try:
                df = get_price_history(data_client, ticker)
                if len(df) < 20:
                    log.warning(f"[{ticker}] Yetersiz veri ({len(df)} gun), atlaniyor.")
                    continue
                signal = build_signal(df, config.TREND_FILTER_ENABLED)
                log.info(
                    f"[{ticker}] skor={signal['composite']} verdict={signal['verdict']} "
                    f"trend={signal['trend_state']} son_fiyat={signal['last_close']:.2f} | {signal['details']}"
                )
                if signal["composite"] >= config.BUY_SCORE_THRESHOLD and (
                    config.MAX_STOCK_PRICE <= 0 or signal["last_close"] <= config.MAX_STOCK_PRICE
                ):
                    place_buy(trading_client, ticker, signal["last_close"], signal.get("atr"))
                else:
                    log.info(f"[{ticker}] Islem yok (BEKLE ya da fiyat filtresine takildi).")
            except Exception as e:
                log.exception(f"[{ticker}] Hata: {e}")


if __name__ == "__main__":
    run_once()
