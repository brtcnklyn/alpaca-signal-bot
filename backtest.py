"""Gerçekçi gün içi backtest: sinyal bar kapanışında, işlem SONRAKİ barın açılışında,
kayma (slippage) dahil, stop/kâr al bar içi kontrol, gün sonunda tüm pozisyonlar kapanır."""
import numpy as np
import pandas as pd

from config import CFG
from risk import CircuitBreaker, position_size


def run(df: pd.DataFrame, probs: pd.Series, start_equity=10_000.0, cfg=CFG):
    d = df.join(probs, how="inner")
    slip = cfg.slippage_bps / 1e4
    cash = start_equity
    pos = {}       # sym -> dict(qty, entry, stop, tp)
    pending = {}   # sym -> 'buy' | 'sell'
    trades, equity_curve = [], []
    cb = CircuitBreaker(start_equity, cfg)
    cur_day = None
    status = "ok"

    by_ts = {ts: g.droplevel("timestamp") for ts, g in d.groupby(level="timestamp")}
    for ts in sorted(by_ts):
        bar = by_ts[ts]
        if ts.date() != cur_day:
            cur_day = ts.date()
            eq = cash + sum(p["qty"] * p["last"] for p in pos.values())
            cb.new_day(eq)
            if status != "kill":
                status = "ok"
        mins = ts.hour * 60 + ts.minute - 570
        flatten = mins >= 390 - cfg.flatten_minutes_before_close - cfg.bar_minutes

        # 1) Bekleyen emirleri bu barın açılışında uygula
        for sym, side in list(pending.items()):
            if sym not in bar.index:
                continue
            r = bar.loc[sym]
            if side == "sell" and sym in pos:
                px = r["open"] * (1 - slip)
                p = pos.pop(sym)
                cash += p["qty"] * px
                trades.append((sym, p["t_in"], ts, p["entry"], px, p["qty"], "sinyal"))
            elif side == "buy" and sym not in pos and status == "ok" and not flatten:
                px = r["open"] * (1 + slip)
                eq = cash + sum(p["qty"] * p["last"] for p in pos.values())
                qty = min(position_size(eq, px, r["atr"], cfg), int(cash // px))
                if qty > 0:
                    cash -= qty * px
                    pos[sym] = dict(qty=qty, entry=px, last=px, t_in=ts,
                                    stop=px - cfg.stop_atr_mult * r["atr"],
                                    tp=px + cfg.take_profit_atr_mult * r["atr"])
            pending.pop(sym, None)

        # 2) Stop / kâr al / gün sonu
        for sym in list(pos):
            if sym not in bar.index:
                continue
            r, p = bar.loc[sym], pos[sym]
            exit_px, why = None, None
            if r["low"] <= p["stop"]:
                exit_px, why = min(r["open"], p["stop"]) * (1 - slip), "stop"
            elif r["high"] >= p["tp"]:
                exit_px, why = max(r["open"], p["tp"]) * (1 - slip), "kar_al"
            elif flatten:
                exit_px, why = r["close"] * (1 - slip), "gun_sonu"
            if exit_px is not None:
                cash += p["qty"] * exit_px
                trades.append((sym, p["t_in"], ts, p["entry"], exit_px, p["qty"], why))
                del pos[sym]
            else:
                p["last"] = r["close"]

        # 3) Devre kesici
        eq = cash + sum(p["qty"] * p["last"] for p in pos.values())
        status = cb.check(eq) if status != "kill" else "kill"
        equity_curve.append((ts, eq))

        # 4) Yeni sinyaller (bir sonraki barda uygulanır)
        if flatten or status != "ok":
            continue
        for sym in bar.index:
            pr = bar.loc[sym, "prob"]
            if sym in pos and pr < cfg.exit_threshold:
                pending[sym] = "sell"
        cands = bar[(bar["prob"] > cfg.long_threshold) & (~bar.index.isin(list(pos)))]
        slots = cfg.max_open_positions - len(pos)
        for sym in cands.sort_values("prob", ascending=False).index[:max(0, slots)]:
            pending[sym] = "buy"

    eqc = pd.Series(dict(equity_curve)).sort_index()
    tr = pd.DataFrame(trades, columns=["sembol", "giris_zamani", "cikis_zamani", "giris", "cikis", "adet", "neden"])
    return eqc, tr


def report(eqc: pd.Series, tr: pd.DataFrame, bench: pd.Series | None = None, start_equity=10_000.0):
    daily = eqc.groupby(eqc.index.date).last()
    dr = daily.pct_change().dropna()
    total = eqc.iloc[-1] / start_equity - 1
    sharpe = np.sqrt(252) * dr.mean() / dr.std() if dr.std() > 0 else 0
    dd = (eqc / eqc.cummax() - 1).min()
    pnl = (tr["cikis"] - tr["giris"]) * tr["adet"] if len(tr) else pd.Series(dtype=float)
    lines = [
        "=" * 50, "BACKTEST SONUÇLARI (hiç görülmemiş veride, walk-forward)", "=" * 50,
        f"Başlangıç / Bitiş     : ${start_equity:,.0f} -> ${eqc.iloc[-1]:,.0f}",
        f"Toplam getiri         : {total:+.2%}",
        f"Yıllık Sharpe         : {sharpe:.2f}  (1.0 üstü iyi, 0 civarı = kenar yok)",
        f"Maksimum düşüş (DD)   : {dd:.2%}",
        f"İşlem sayısı          : {len(tr)}",
        f"Kazanma oranı         : {(pnl > 0).mean():.1%}" if len(tr) else "Kazanma oranı: -",
        f"Ortalama işlem k/z    : ${pnl.mean():.2f}" if len(tr) else "",
    ]
    if len(tr):
        lines.append("Çıkış nedenleri       : " + ", ".join(f"{k}={v}" for k, v in tr["neden"].value_counts().items()))
    if bench is not None:
        lines.append(f"SPY al-tut (aynı dönem): {bench.iloc[-1] / bench.iloc[0] - 1:+.2%}")
    txt = "\n".join(l for l in lines if l)
    print(txt)
    return txt
