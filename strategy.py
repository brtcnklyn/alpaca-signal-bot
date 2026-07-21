"""
strategy.py
Fiyat verisinden kompozit al/sat/bekle sinyali üretir.
Aynı mantık: SIGNAL DESK panelinde kullandığımız SMA / RSI / MACD / Bollinger skorlaması.
Bu göstergeler GÜNLÜK kapanış verisine dayanır -> gün içi (intraday) karar için uygun değildir.
"""

import pandas as pd
from indicators import sma, rsi, macd, bollinger, last_two


def build_signal(df: pd.DataFrame) -> dict:
    """
    df: 'close' sütunu olan, eskiden yeniye sıralı bir DataFrame.
    Dönüş: composite skor (-100..100), verdict (metin), ve gösterge detayları.
    """
    closes = df["close"]

    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    r = rsi(closes, 14)
    _, _, hist = macd(closes)
    upper, mid, lower = bollinger(closes, 20, 2.0)

    scores = {}
    details = {}

    # --- SMA trend / kesişim ---
    s20, s20_prev = last_two(sma20)
    s50, s50_prev = last_two(sma50)
    if s20 is not None and s50 is not None:
        crossed_up = s20_prev is not None and s50_prev is not None and s20_prev <= s50_prev and s20 > s50
        crossed_down = s20_prev is not None and s50_prev is not None and s20_prev >= s50_prev and s20 < s50
        if crossed_up:
            scores["sma"] = 100
            details["sma"] = "Altin Kesisim (SMA20 yukari kesti)"
        elif crossed_down:
            scores["sma"] = -100
            details["sma"] = "Olum Kesisimi (SMA20 asagi kesti)"
        elif s20 > s50:
            scores["sma"] = 40
            details["sma"] = f"Yukselis trendi (SMA20 {s20:.2f} > SMA50 {s50:.2f})"
        else:
            scores["sma"] = -40
            details["sma"] = f"Dusus trendi (SMA20 {s20:.2f} < SMA50 {s50:.2f})"
    else:
        details["sma"] = "Yetersiz veri (SMA50 icin >=50 gun gerekli)"

    # --- RSI ---
    rv, _ = last_two(r)
    if rv is not None:
        if rv < 30:
            scores["rsi"] = 70
            details["rsi"] = f"Asiri satim (RSI {rv:.1f})"
        elif rv > 70:
            scores["rsi"] = -70
            details["rsi"] = f"Asiri alim (RSI {rv:.1f})"
        elif rv <= 45:
            scores["rsi"] = 20
            details["rsi"] = f"Zayif bolge (RSI {rv:.1f})"
        elif rv >= 55:
            scores["rsi"] = -20
            details["rsi"] = f"Guclu bolge (RSI {rv:.1f})"
        else:
            scores["rsi"] = 0
            details["rsi"] = f"Notr (RSI {rv:.1f})"
    else:
        details["rsi"] = "Yetersiz veri"

    # --- MACD histogram kesişimi ---
    hv, hv_prev = last_two(hist)
    if hv is not None:
        crossed_up = hv_prev is not None and hv_prev <= 0 and hv > 0
        crossed_down = hv_prev is not None and hv_prev >= 0 and hv < 0
        if crossed_up:
            scores["macd"] = 100
            details["macd"] = "MACD yukselis kesisimi"
        elif crossed_down:
            scores["macd"] = -100
            details["macd"] = "MACD dusus kesisimi"
        elif hv > 0:
            scores["macd"] = 40
            details["macd"] = f"Pozitif momentum (hist {hv:.2f})"
        else:
            scores["macd"] = -40
            details["macd"] = f"Negatif momentum (hist {hv:.2f})"
    else:
        details["macd"] = "Yetersiz veri"

    # --- Bollinger ---
    uv, _ = last_two(upper)
    lv, _ = last_two(lower)
    last_close = float(closes.iloc[-1])
    if uv is not None and lv is not None and uv != lv:
        pos = (last_close - lv) / (uv - lv)
        if pos > 0.95:
            scores["bb"] = -60
            details["bb"] = "Ust banda dayandi (asiri alim riski)"
        elif pos < 0.05:
            scores["bb"] = 60
            details["bb"] = "Alt banda dayandi (asiri satim firsati)"
        elif pos > 0.8:
            scores["bb"] = -30
            details["bb"] = "Ust banda yakin"
        elif pos < 0.2:
            scores["bb"] = 30
            details["bb"] = "Alt banda yakin"
        else:
            scores["bb"] = 0
            details["bb"] = "Bant ortasi (notr)"
    else:
        details["bb"] = "Yetersiz veri"

    if scores:
        composite = sum(scores.values()) / len(scores)
    else:
        composite = 0.0

    if composite >= 50:
        verdict = "GUCLU_AL"
    elif composite >= 20:
        verdict = "AL"
    elif composite > -20:
        verdict = "BEKLE"
    elif composite > -50:
        verdict = "SAT"
    else:
        verdict = "GUCLU_SAT"

    return {
        "composite": round(composite, 1),
        "verdict": verdict,
        "last_close": last_close,
        "scores": scores,
        "details": details,
        "data_points": len(closes),
    }
