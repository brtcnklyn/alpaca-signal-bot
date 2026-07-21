"""
indicators.py
Teknik gösterge hesaplamaları: SMA, EMA, RSI, MACD, Bollinger Bantları.
Girdi: pandas.Series (kapanış fiyatları, eskiden yeniye sıralı)
"""

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(series: pd.Series, period: int = 20, mult: float = 2.0):
    mid = sma(series, period)
    std = series.rolling(window=period).std()
    upper = mid + mult * std
    lower = mid - mult * std
    return upper, mid, lower


def last_two(series: pd.Series):
    """Son iki geçerli (NaN olmayan) değeri döndürür: (son, önceki_son)."""
    valid = series.dropna()
    if len(valid) == 0:
        return None, None
    if len(valid) == 1:
        return float(valid.iloc[-1]), None
    return float(valid.iloc[-1]), float(valid.iloc[-2])
