"""Alpaca'dan geçmiş mum verisi çekme (+ test için sentetik veri)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config import CFG


def fetch_bars(symbols, days=None, minutes=None) -> pd.DataFrame:
    """MultiIndex (symbol, timestamp) ile OHLCV döndürür. Sadece seans içi barlar."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    days = days or CFG.history_days
    minutes = minutes or CFG.bar_minutes
    client = StockHistoricalDataClient(CFG.api_key, CFG.secret_key)
    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(minutes, TimeFrameUnit.Minute),
        start=datetime.now(timezone.utc) - timedelta(days=days),
        end=datetime.now(timezone.utc) - timedelta(minutes=16),  # ücretsiz veri 15 dk gecikmeli
        feed="iex",
    )
    df = client.get_stock_bars(req).df
    return _regular_session(df)


def fetch_crypto_bars(symbols, days=None, minutes=None) -> pd.DataFrame:
    """Kripto 5 dk mumları (7/24, gecikmesiz). Sembol biçimi 'BTC/USD'."""
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    days = days or CFG.crypto_history_days
    minutes = minutes or CFG.bar_minutes
    client = CryptoHistoricalDataClient(CFG.api_key, CFG.secret_key)
    req = CryptoBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(minutes, TimeFrameUnit.Minute),
        start=datetime.now(timezone.utc) - timedelta(days=days),
        end=datetime.now(timezone.utc),
    )
    df = client.get_crypto_bars(req).df
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def _regular_session(df: pd.DataFrame) -> pd.DataFrame:
    ts = df.index.get_level_values("timestamp").tz_convert("America/New_York")
    mins = ts.hour * 60 + ts.minute
    mask = (mins >= 9 * 60 + 30) & (mins < 16 * 60)
    out = df[mask].copy()
    out.index = pd.MultiIndex.from_arrays(
        [out.index.get_level_values("symbol"), ts[mask]], names=["symbol", "timestamp"])
    return out[["open", "high", "low", "close", "volume"]]


def synthetic_bars(symbols, days=60, minutes=5, seed=0) -> pd.DataFrame:
    """İnternetsiz test için gerçekçi rastgele yürüyüş verisi (sinyal İÇERMEZ)."""
    rng = np.random.default_rng(seed)
    frames = []
    sessions = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    per_day = 390 // minutes
    for s in symbols:
        price = rng.uniform(50, 500)
        rows = []
        for d in sessions:
            start = pd.Timestamp(d.date()).tz_localize("America/New_York") + pd.Timedelta(hours=9, minutes=30)
            for i in range(per_day):
                r = rng.normal(0, 0.0015)
                o = price
                c = price * (1 + r)
                h = max(o, c) * (1 + abs(rng.normal(0, 0.0006)))
                l = min(o, c) * (1 - abs(rng.normal(0, 0.0006)))
                rows.append((s, start + pd.Timedelta(minutes=minutes * i), o, h, l, c, rng.integers(1e4, 1e5)))
                price = c
        frames.append(pd.DataFrame(rows, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]))
    return pd.concat(frames).set_index(["symbol", "timestamp"]).sort_index()
