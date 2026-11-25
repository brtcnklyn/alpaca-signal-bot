"""Trend takibi botu (günlük). Kurallar trend.py'de; backtest ile birebir aynı.
  Hisse : seans açılmadan önce dünkü kapanışa göre sinyal -> piyasa emri açılışta dolar.
  Kripto: her gün 00:10 UTC'den sonra, biten günün kapanışına göre sinyal -> hemen piyasa emri.
Aynı gün iki kez çalışsa da çift emir olmaz: her emrin client_order_id'si tarih + sembol içerir.
Hesap ikiye bölünür: hisse %70, kripto %30 (pozisyon boyutları bu paylara göre)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from config import CFG
from trend import CRYPTO, STOCK, indicators, regime, shares_for

STOCK_SHARE, CRYPTO_SHARE = 0.70, 0.30


def log(msg):
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    with open("bot_log.txt", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _wide(df: pd.DataFrame, dates) -> dict:
    df = df.copy()
    df["d"] = dates
    out = {}
    for col in ("open", "high", "low", "close"):
        out[col] = df.reset_index().pivot_table(index="d", columns="symbol", values=col, aggfunc="last").sort_index()
    return out


def stock_daily(symbols, days=450):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(CFG.api_key, CFG.secret_key)
    end = datetime.now(timezone.utc) - timedelta(minutes=16)
    last_err = None
    for feed in ("sip", "iex"):
        try:
            req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, adjustment="all",
                                   start=end - timedelta(days=days), end=end, feed=feed)
            df = client.get_stock_bars(req).df
            break
        except Exception as e:  # ücretsiz planda SIP reddedilirse IEX
            last_err = e
    else:
        raise last_err
    ts = df.index.get_level_values("timestamp").tz_convert("America/New_York")
    return _wide(df, ts.date)


def crypto_daily(symbols, days=320):
    """Saatlik mumlardan UTC günlük mum (yfinance BTC-USD günleriyle aynı tanım)."""
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = CryptoHistoricalDataClient(CFG.api_key, CFG.secret_key)
    end = datetime.now(timezone.utc)
    df = client.get_crypto_bars(CryptoBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Hour,
                                                  start=end - timedelta(days=days), end=end)).df
    ts = df.index.get_level_values("timestamp").tz_convert("UTC")
    df = df.copy()
    df["d"] = ts.date
    g = df.reset_index().groupby(["d", "symbol"])
    daily = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                          "low": g["low"].min(), "close": g["close"].last()})
    return {c: daily[c].unstack("symbol").sort_index() for c in daily.columns}


def _signals(w, upto, reg_sym, p):
    """'upto' tarihinden ÖNCEKİ son tamamlanmış günün sinyalleri."""
    w = {k: v[pd.to_datetime(v.index) < pd.Timestamp(upto)] for k, v in w.items()}
    ind = indicators(w["close"], w["high"], w["low"], p)
    last = w["close"].index[-1]
    reg_ok = bool(regime(w["close"][reg_sym]).iloc[-1]) if reg_sym in w["close"] else False
    c = w["close"].loc[last]
    exits = {s for s, v in ind["exit"].loc[last].items() if bool(v)}
    entries = [s for s, v in ind["entry"].loc[last].items() if bool(v)]
    strength = ((c[entries] / ind["ma"].loc[last][entries] - 1) / (ind["atr"].loc[last][entries] / c[entries]))
    entries = list(strength.sort_values(ascending=False).index)
    return last, reg_ok, entries, exits, ind["atr"].loc[last], c, ind["chand"].loc[last]


def _submit(tc, cid, **kw):
    from alpaca.trading.requests import MarketOrderRequest
    if os.getenv("KURU") == "1":  # deneme: emir gönderme, sadece yaz
        log(f"[KURU] {cid} {kw}")
        return True
    try:
        tc.submit_order(MarketOrderRequest(client_order_id=cid, **kw))
        return True
    except Exception as e:
        msg = str(e)
        if "client_order_id" in msg and ("unique" in msg or "exist" in msg):
            log(f"{cid} zaten gönderilmiş, atlandı")
        else:
            log(f"{cid} emri reddedildi: {msg[:200]}")
        return False


def _acls(p):
    return getattr(p.asset_class, "value", str(p.asset_class))


def run_stocks(tc) -> str:
    from alpaca.trading.enums import OrderSide, TimeInForce

    clock = tc.get_clock()
    target = clock.timestamp.date() if clock.is_open else clock.next_open.date()
    universe = list(dict.fromkeys(["SPY"] + CFG.symbols))
    w = stock_daily(universe)
    last, reg_ok, entries, exits, atr, close, chand = _signals(w, target, "SPY", STOCK)
    acct = tc.get_account()
    sleeve = float(acct.equity) * STOCK_SHARE
    positions = {p.symbol: p for p in tc.get_all_positions() if _acls(p) == "us_equity"}
    pending = {o.symbol for o in tc.get_orders()}
    tag = target.strftime("%y%m%d")
    sold, bought = [], []

    for s, p in positions.items():
        if s in exits:
            if _submit(tc, f"trh-{tag}-s-{s}", symbol=s, qty=abs(float(p.qty)), side=OrderSide.SELL,
                       time_in_force=TimeInForce.DAY):
                sold.append(f"{s} (stop {chand[s]:.2f}, k/z ${float(p.unrealized_pl):+,.0f})")
    held = len(positions) - len(sold)
    invested = sum(float(p.market_value) for s, p in positions.items() if s not in exits)
    if reg_ok:
        for s in entries:
            if held >= STOCK.max_pos:
                break
            if s in positions or s in pending:
                continue
            q = int(shares_for(sleeve, close[s], atr[s], STOCK))
            cost = q * close[s] * 1.01
            if q <= 0 or invested + cost > sleeve:
                continue
            if _submit(tc, f"trh-{tag}-b-{s}", symbol=s, qty=q, side=OrderSide.BUY, time_in_force=TimeInForce.DAY):
                bought.append(f"{s} x{q} (~${q * close[s]:,.0f}, ilk stop ~{close[s] - STOCK.chand_mult * atr[s]:.2f})")
                held += 1
                invested += cost
    when = "açılışta" if not clock.is_open else "şimdi"
    lines = [f"<b>📊 Trend botu — Hisse</b> ({last:%d.%m} kapanışına göre, emirler {when})",
             f"Piyasa filtresi (SPY > 200 gün ort.): {'✅ alım serbest' if reg_ok else '⛔ yeni alım yok'}"]
    lines += [f"🟢 AL: {b}" for b in bought] + [f"🔴 SAT: {x}" for x in sold]
    if not bought and not sold:
        lines.append("Bugün yeni sinyal yok, pozisyonlar korunuyor.")
    keep = [s for s in positions if s not in exits]
    if keep:
        lines.append("Elde: " + ", ".join(f"{s} (stop {chand.get(s, float('nan')):.2f})" for s in keep))
    return "\n".join(lines)


def run_crypto(tc) -> str:
    from alpaca.trading.enums import AssetClass, OrderSide, TimeInForce
    from alpaca.trading.requests import GetAssetsRequest

    tradable = {a.symbol for a in tc.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO)) if a.tradable}
    syms = [s for s in CFG.crypto_symbols if s in tradable]
    today = datetime.now(timezone.utc).date()
    w = crypto_daily(syms)
    last, reg_ok, entries, exits, atr, close, chand = _signals(w, today, "BTC/USD", CRYPTO)
    acct = tc.get_account()
    sleeve = float(acct.equity) * CRYPTO_SHARE
    cash = float(acct.non_marginable_buying_power or acct.cash)
    norm = {s.replace("/", ""): s for s in syms}
    positions = {norm[p.symbol]: p for p in tc.get_all_positions()
                 if _acls(p) == "crypto" and p.symbol in norm}
    tag = today.strftime("%y%m%d")
    sold, bought = [], []
    for s, p in positions.items():
        if s in exits:
            q = float(p.qty_available or p.qty)
            if _submit(tc, f"trk-{tag}-s-{s.replace('/', '')}", symbol=s, qty=q, side=OrderSide.SELL,
                       time_in_force=TimeInForce.GTC):
                sold.append(f"{s} (stop {chand[s]:.6g}, k/z ${float(p.unrealized_pl):+,.0f})")
    held = len(positions) - len(sold)
    invested = sum(float(p.market_value) for s, p in positions.items() if s not in exits)
    if reg_ok:
        for s in entries:
            if held >= CRYPTO.max_pos:
                break
            if s in positions:
                continue
            notional = round(min(shares_for(sleeve, close[s], atr[s], CRYPTO) * close[s],
                                 sleeve - invested, cash * 0.95), 2)
            if notional < 10:
                continue
            if _submit(tc, f"trk-{tag}-b-{s.replace('/', '')}", symbol=s, notional=notional,
                       side=OrderSide.BUY, time_in_force=TimeInForce.GTC):
                bought.append(f"{s} ${notional:,.0f} (ilk stop ~{close[s] - CRYPTO.chand_mult * atr[s]:.6g})")
                held += 1
                invested += notional
                cash -= notional
    lines = [f"<b>🪙 Trend botu — Kripto</b> ({last:%d.%m} günü kapanışına göre)",
             f"Piyasa filtresi (BTC > 200 gün ort.): {'✅ alım serbest' if reg_ok else '⛔ yeni alım yok'}"]
    lines += [f"🟢 AL: {b}" for b in bought] + [f"🔴 SAT: {x}" for x in sold]
    if not bought and not sold:
        lines.append("Bugün yeni sinyal yok, pozisyonlar korunuyor.")
    keep = [s for s in positions if s not in exits]
    if keep:
        lines.append("Elde: " + ", ".join(f"{s} (stop {chand.get(s, float('nan')):.6g})" for s in keep))
    return "\n".join(lines)


if __name__ == "__main__":
    from alpaca.trading.client import TradingClient

    from telegram_rapor import send

    if not CFG.paper:
        sys.exit("Trend botu yalnızca SANAL hesapta çalıştırılır (PAPER=true).")
    tc = TradingClient(CFG.api_key, CFG.secret_key, paper=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "hepsi"
    for name, fn in (("hisse", run_stocks), ("kripto", run_crypto)):
        if which in (name, "hepsi"):
            msg = fn(tc)
            print(msg)
            if "--sessiz" not in sys.argv:
                send(msg)
