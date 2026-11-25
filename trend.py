"""Çok günlük trend takibi stratejisi (günlük mumlar). Hem backtest hem canlı bot aynı kuralları kullanır.

Kurallar (önceden sabitlendi, geçmiş veriye göre ince ayar yapılmadı):
  GİRİŞ  : kapanış, önceki 55 günün en yüksek kapanışını aşar (kırılım)
           VE kapanış 200 günlük ortalamanın üstünde
           VE piyasa filtresi olumlu (hisse: SPY > 200 gün ort., kripto: BTC > 200 gün ort.)
  ÇIKIŞ  : kapanış < son 22 günün en yükseği - 3 x ATR(22)   (iz süren "chandelier" stop)
  BOYUT  : stop olursa sermayenin 'risk' kadarı kaybedilecek şekilde, tek pozisyon en fazla 'cap'
  İŞLEM  : sinyal günün kapanışında oluşur, ertesi gün (açılışta) uygulanır.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TrendParams:
    breakout: int = 55
    trend_ma: int = 200
    chand_n: int = 22
    chand_mult: float = 3.0
    risk: float = 0.01        # pozisyon başına risk (sermaye oranı)
    cap: float = 0.10         # tek pozisyon üst sınırı
    max_pos: int = 10
    cost: float = 0.0005      # tek yön maliyet (komisyon + kayma)


STOCK = TrendParams()
CRYPTO = TrendParams(risk=0.005, cap=0.08, max_pos=5, cost=0.0025)


def indicators(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, p: TrendParams) -> dict:
    """Satır = gün, sütun = sembol."""
    prev_c = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_c).abs(), (low - prev_c).abs()]).groupby(level=0).max()
    tr = tr.reindex(close.index)
    atr = tr.rolling(p.chand_n, min_periods=p.chand_n).mean()
    hh_break = close.shift(1).rolling(p.breakout, min_periods=p.breakout).max()
    ma = close.rolling(p.trend_ma, min_periods=p.trend_ma).mean()
    chand = high.rolling(p.chand_n, min_periods=p.chand_n).max() - p.chand_mult * atr
    return {"close": close, "atr": atr, "entry": (close > hh_break) & (close > ma),
            "exit": close < chand, "chand": chand, "ma": ma}


def regime(close: pd.Series, n: int = 200) -> pd.Series:
    """Piyasa filtresi: endeks / BTC 200 günlük ortalamanın üstünde mi?"""
    return close > close.rolling(n, min_periods=n).mean()


def shares_for(equity: float, price: float, atr: float, p: TrendParams) -> float:
    if not (atr > 0 and price > 0):
        return 0.0
    by_risk = equity * p.risk / (p.chand_mult * atr)
    by_cap = equity * p.cap / price
    return max(0.0, min(by_risk, by_cap))


def backtest(open_: pd.DataFrame, close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
             reg: pd.Series, p: TrendParams, start_equity=100_000.0, fractional=False):
    """Günlük simülasyon. (özsermaye eğrisi, işlem listesi) döndürür."""
    ind = indicators(close, high, low, p)
    days = close.index
    cash, pos, trades, curve = start_equity, {}, [], []
    pend_buy, pend_sell = [], []
    reg = reg.reindex(days).fillna(False)
    for i, d in enumerate(days):
        o = open_.loc[d]
        # 1) Dünkü sinyalleri bugün açılışta uygula
        for s in pend_sell:
            if s in pos and np.isfinite(o.get(s, np.nan)):
                q, e, t0 = pos.pop(s)
                px = o[s] * (1 - p.cost)
                cash += q * px
                trades.append((s, t0, d, e, px, q))
        for s in pend_buy:
            if s in pos or len(pos) >= p.max_pos or not np.isfinite(o.get(s, np.nan)):
                continue
            eq = cash + sum(q * close.iloc[i - 1][k] for k, (q, _, _) in pos.items())
            q = shares_for(eq, o[s], ind["atr"].iloc[i - 1][s], p)
            q = q if fractional else np.floor(q)
            px = o[s] * (1 + p.cost)
            q = min(q, cash / px) if fractional else min(q, np.floor(cash / px))
            if q > 0:
                cash -= q * px
                pos[s] = (q, px, d)
        pend_buy, pend_sell = [], []
        # 2) Bugünün kapanışında sinyal üret
        c = close.loc[d]
        eq = cash + sum(q * (c[k] if np.isfinite(c[k]) else e) for k, (q, e, _) in pos.items())
        curve.append((d, eq))
        ex = ind["exit"].loc[d]
        pend_sell = [s for s in pos if bool(ex.get(s, False))]
        if reg.loc[d]:
            en = ind["entry"].loc[d]
            cands = [s for s in en.index[en.fillna(False).values] if s not in pos]
            # en güçlü kırılım önce: 200 gün ortalamasından uzaklık / volatilite
            strength = ((c[cands] / ind["ma"].loc[d][cands] - 1) / (ind["atr"].loc[d][cands] / c[cands]))
            pend_buy = list(strength.sort_values(ascending=False).index)
    eqs = pd.Series(dict(curve))
    return eqs, pd.DataFrame(trades, columns=["sembol", "giris_t", "cikis_t", "giris", "cikis", "adet"])


def stats(eq: pd.Series, trades: pd.DataFrame | None = None, periods=252) -> dict:
    r = eq.pct_change().dropna()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    out = {
        "yillik_getiri": (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan,
        "sharpe": r.mean() / r.std() * np.sqrt(periods) if r.std() > 0 else np.nan,
        "maks_dusus": (eq / eq.cummax() - 1).min(),
    }
    if trades is not None and len(trades):
        pnl = trades["cikis"] / trades["giris"] - 1
        out.update(islem=len(trades), isabet=(pnl > 0).mean(), ort_islem=pnl.mean())
    return out
