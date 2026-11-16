"""Qlib Alpha158'den esinlenen gün içi teknik özellikler.
Tümü sadece GEÇMİŞ veriyi kullanır (geleceği görme / look-ahead yok)."""
import numpy as np
import pandas as pd

FEATURES = [
    "ret_1", "ret_3", "ret_6", "ret_12", "ret_24",
    "vol_12", "vol_48", "atr_pct", "rsi_14",
    "dist_vwap", "dist_ma20", "dist_ma60", "ma20_slope",
    "vol_z", "range_pos_24", "bar_body", "upper_wick", "lower_wick",
    "minute_of_day", "day_ret", "mkt_ret_6", "rel_ret_6",
]


def _rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / (dn + 1e-12))


def _one_symbol(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy()
    c, h, l, o, v = g["close"], g["high"], g["low"], g["open"], g["volume"]
    lr = np.log(c).diff()
    f = pd.DataFrame(index=g.index)
    for n in (1, 3, 6, 12, 24):
        f[f"ret_{n}"] = np.log(c / c.shift(n))
    f["vol_12"] = lr.rolling(12).std()
    f["vol_48"] = lr.rolling(48).std()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    g["atr"] = tr.rolling(14).mean()
    f["atr_pct"] = g["atr"] / c
    f["rsi_14"] = _rsi(c) / 100
    day = g.index.get_level_values("timestamp").date
    pv = (c * v).groupby(day).cumsum()
    vv = v.groupby(day).cumsum()
    f["dist_vwap"] = c / (pv / vv) - 1
    ma20, ma60 = c.rolling(20).mean(), c.rolling(60).mean()
    f["dist_ma20"] = c / ma20 - 1
    f["dist_ma60"] = c / ma60 - 1
    f["ma20_slope"] = ma20.pct_change(5)
    f["vol_z"] = (v - v.rolling(48).mean()) / (v.rolling(48).std() + 1e-9)
    hh, ll = h.rolling(24).max(), l.rolling(24).min()
    f["range_pos_24"] = (c - ll) / (hh - ll + 1e-9)
    rng = (h - l) + 1e-9
    f["bar_body"] = (c - o) / rng
    f["upper_wick"] = (h - np.maximum(c, o)) / rng
    f["lower_wick"] = (np.minimum(c, o) - l) / rng
    ts = g.index.get_level_values("timestamp")
    f["minute_of_day"] = ((ts.hour * 60 + ts.minute) - 570) / 390
    day_open = o.groupby(day).transform("first")
    f["day_ret"] = c / day_open - 1
    f["atr"] = g["atr"]
    f["open"], f["high"], f["low"], f["close"] = o, h, l, c
    return f


def build_features(bars: pd.DataFrame) -> pd.DataFrame:
    parts = [_one_symbol(g) for _, g in bars.groupby(level="symbol", group_keys=False)]
    f = pd.concat(parts).sort_index()
    # Piyasa geneli (tüm evrenin ortalaması) ve göreli güç
    mkt = f.groupby(level="timestamp")["ret_6"].mean().rename("mkt_ret_6")
    f = f.join(mkt, on="timestamp")
    f["rel_ret_6"] = f["ret_6"] - f["mkt_ret_6"]
    return f


def add_label(f: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Hedef: 'horizon' bar sonra, maliyet sonrası anlamlı yükseliş oldu mu? (aynı gün içinde)"""
    f = f.copy()
    ts = f.index.get_level_values("timestamp")
    sym = f.index.get_level_values("symbol")
    key = pd.Series(list(zip(sym, ts.date)), index=f.index)
    fut = f.groupby(key.values)["close"].shift(-horizon)
    f["fwd_ret"] = fut / f["close"] - 1
    # Sadece gürültüyü geçen hareketleri pozitif say (0.25 ATR üstü)
    f["label"] = (f["fwd_ret"] > 0.25 * f["atr"] / f["close"]).astype(float)
    f.loc[f["fwd_ret"].isna(), "label"] = np.nan
    return f
