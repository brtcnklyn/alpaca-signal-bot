"""Önce BUNU çalıştır. Model, hiç görmediği günlerde gerçekten para kazanıyor mu?
    python run_backtest.py            -> Alpaca'dan gerçek veri (API anahtarı gerekir)
    python run_backtest.py --demo     -> internetsiz sentetik veri (sadece kodun çalıştığını gösterir)"""
import argparse

from config import CFG
from features import add_label, build_features
from model import walk_forward
import backtest as BT

ap = argparse.ArgumentParser()
ap.add_argument("--demo", action="store_true")
ap.add_argument("--sermaye", type=float, default=10_000)
args = ap.parse_args()

if args.demo:
    from data import synthetic_bars
    bars = synthetic_bars(CFG.symbols[:6], days=70)
else:
    from data import fetch_bars
    bars = fetch_bars(CFG.symbols)

print(f"{bars.index.get_level_values('symbol').nunique()} sembol, {len(bars):,} bar yüklendi")
df = add_label(build_features(bars), CFG.horizon_bars)
probs = walk_forward(df)
eqc, trades = BT.run(df, probs, start_equity=args.sermaye)

bench = None
if "SPY" in bars.index.get_level_values("symbol"):
    spy = bars.xs("SPY", level="symbol")["close"]
    bench = spy.loc[spy.index >= eqc.index[0]]
txt = BT.report(eqc, trades, bench, args.sermaye)

trades.to_csv("backtest_islemler.csv", index=False)
eqc.to_csv("backtest_ozsermaye.csv", header=["ozsermaye"])
open("backtest_rapor.txt", "w", encoding="utf-8").write(txt)
print("\nDosyalar: backtest_rapor.txt, backtest_islemler.csv, backtest_ozsermaye.csv")
print("KURAL: Sharpe < 1 veya getiri SPY'ın altındaysa canlıya GEÇME. Ayarları değiştir, tekrar test et.")
