"""
screener.py
Bir hisse listesini (universe) tarar, her biri için sinyal skoru hesaplar
ve en güçlü AL sinyali verenleri sıralayıp döndürür.
"""

import logging
from alpaca.data.historical import StockHistoricalDataClient

from strategy import build_signal

log = logging.getLogger("signal-bot")


def scan_universe(get_price_history_fn, data_client: StockHistoricalDataClient, universe: list,
                   trend_filter_enabled: bool = True) -> list:
    """
    get_price_history_fn: bot.py'deki get_price_history fonksiyonu (bagimlilik disaridan verilir)
    Donus: [{"ticker": ..., "signal": {...}}, ...] -> composite skora gore buyukten kucuge sirali
    """
    results = []
    for ticker in universe:
        try:
            df = get_price_history_fn(data_client, ticker)
            if len(df) < 55:  # SMA50 + biraz pay
                continue
            signal = build_signal(df, trend_filter_enabled)
            results.append({"ticker": ticker, "signal": signal})
        except Exception as e:
            log.warning(f"[TARAMA] {ticker} atlandi: {e}")
            continue

    results.sort(key=lambda r: r["signal"]["composite"], reverse=True)
    return results


def pick_buy_candidates(scan_results: list, top_n: int, already_held: set, score_threshold: float,
                         max_price: float = 0) -> list:
    """
    Zaten elde olmayan, kompozit skoru score_threshold'un USTUNDE olan (ve max_price>0 ise
    fiyati max_price'in ALTINDA/ESIT olan) en guclu top_n hisseyi secer.
    """
    candidates = [
        r for r in scan_results
        if r["ticker"] not in already_held
        and r["signal"]["composite"] >= score_threshold
        and (max_price <= 0 or r["signal"]["last_close"] <= max_price)
    ]
    return candidates[:top_n]
