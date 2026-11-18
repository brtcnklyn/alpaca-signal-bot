"""Canlı döngü. Varsayılan: Alpaca SANAL (paper) hesap.
Gerçek para için: .env içinde PAPER=false  VE  python live_trader.py --live-onay
Her 5 dakikada: veri çek -> özellik -> tahmin -> risk kontrol -> braket emir (stop + kâr al)."""
import argparse
import csv
import sys
import time
from datetime import datetime

import pandas as pd

from telegram_rapor import send as tg

import model as M
from config import CFG
from data import fetch_bars
from features import FEATURES, build_features
from risk import CircuitBreaker, position_size


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    with open("bot_log.txt", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def journal(row):
    new = not pd.io.common.file_exists("islemler.csv")
    with open("islemler.csv", "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["zaman", "sembol", "yon", "adet", "fiyat_tahmini", "olasilik", "stop", "kar_al", "mod"])
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-onay", action="store_true", help="Gerçek parayla işlem yapmayı onaylıyorum")
    ap.add_argument("--max-dakika", type=int, default=0,
                    help="Bu kadar dakika sonra çık (GitHub Actions 6 saat sınırı için). 0 = sınırsız")
    args = ap.parse_args()

    if not CFG.api_key:
        sys.exit("ALPACA_API_KEY yok. .env dosyasını doldur (README'ye bak).")
    if not CFG.paper and not args.live_onay:
        sys.exit("PAPER=false ama --live-onay verilmedi. Gerçek para için ikisi birden gerekli.")

    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

    tc = TradingClient(CFG.api_key, CFG.secret_key, paper=CFG.paper)
    mode = "SANAL" if CFG.paper else "GERCEK PARA"
    acct = tc.get_account()
    log(f"Bot başladı | mod={mode} | özsermaye=${float(acct.equity):,.2f}")

    clf = M.load()
    last_train = None
    started = time.time()
    cb = CircuitBreaker(float(acct.equity))
    # Zirveyi Alpaca geçmişinden al: bot her çalıştığında sıfırlanmasın
    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        ph = tc.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
        cb.peak = max([v for v in ph.equity if v] + [float(acct.equity)])
    except Exception as e:
        log(f"Portföy geçmişi alınamadı: {e!r}")
    errors = 0
    cb.new_day(float(acct.last_equity))
    current_day = None

    while True:
        if args.max_dakika and (time.time() - started) / 60 >= args.max_dakika:
            log("Süre sınırı doldu, çıkılıyor (pozisyonlar stop/kâr-al emirleriyle korunuyor).")
            return
        try:
            clock = tc.get_clock()
            if not clock.is_open:
                wait = (clock.next_open - clock.timestamp).total_seconds()
                if args.max_dakika and wait > 3 * 3600:
                    log("Bugünkü seans bitti, çıkılıyor.")
                    return
                log(f"Piyasa kapalı. {wait / 3600:.1f} saat sonra açılış.")
                time.sleep(min(max(wait, 60), 1800))
                continue

            today = clock.timestamp.date()
            if clf is None or last_train is None or (today - last_train).days >= CFG.retrain_every_days:
                log("Model eğitiliyor (son günlerin verisiyle)...")
                from features import add_label
                hist = add_label(build_features(fetch_bars(CFG.symbols)), CFG.horizon_bars)
                clf = M.train(hist)
                M.save(clf)
                last_train = today
                tg(f"📈 Bot seansta, tarama başladı ({mode}). Özsermaye ${float(tc.get_account().equity):,.2f}")

            acct = tc.get_account()
            equity = float(acct.equity)
            if acct.trading_blocked or acct.account_blocked:
                log("Hesap işlem için bloke. Bekleniyor.")
                time.sleep(300)
                continue
            if today != current_day:
                current_day = today
                cb.new_day(float(acct.last_equity))
            status = cb.check(equity)

            mins_to_close = (clock.next_close - clock.timestamp).total_seconds() / 60
            positions = {p.symbol: p for p in tc.get_all_positions()}

            # Gün sonu veya kill: hepsini kapat
            if mins_to_close <= CFG.flatten_minutes_before_close or status == "kill":
                if positions:
                    log(f"Tüm pozisyonlar kapatılıyor (neden: {'gun_sonu' if status != 'kill' else 'MAKS DÜŞÜŞ - BOT DURDU'})")
                    tc.close_all_positions(cancel_orders=True)
                if status == "kill":
                    tg(f"🛑 <b>BOT DURDU</b>: zirveden %{CFG.max_drawdown_kill*100:.0f} düşüş limiti aşıldı. "
                       f"Tüm pozisyonlar kapatıldı. Özsermaye ${equity:,.2f}")
                    sys.exit("Maksimum düşüş limiti aşıldı. Bot durdu; stratejiyi gözden geçir.")
                time.sleep(60)
                continue

            # Tahmin
            feats = build_features(fetch_bars(CFG.symbols, days=7))
            latest = feats.groupby(level="symbol").tail(1).dropna(subset=FEATURES)
            latest = latest.droplevel("timestamp")
            latest["prob"] = clf.predict_proba(latest[FEATURES])[:, 1]

            # Çıkışlar
            for sym, p in positions.items():
                if sym in latest.index and latest.loc[sym, "prob"] < CFG.exit_threshold:
                    log(f"ÇIKIŞ sinyali {sym} (olasılık {latest.loc[sym, 'prob']:.2f})")
                    tc.close_position(sym)
                    journal([datetime.now(), sym, "SAT", p.qty, latest.loc[sym, "close"],
                             round(latest.loc[sym, "prob"], 3), "", "", mode])

            # Girişler
            if status == "ok":
                open_orders = {o.symbol for o in tc.get_orders()}
                slots = CFG.max_open_positions - len(positions)
                cands = latest[(latest["prob"] > CFG.long_threshold)
                               & ~latest.index.isin(list(positions) + list(open_orders))]
                for sym, r in cands.sort_values("prob", ascending=False).head(max(0, slots)).iterrows():
                    qty = position_size(equity, r["close"], r["atr"])
                    qty = min(qty, int(float(acct.buying_power) // r["close"]))
                    if qty <= 0:
                        continue
                    stop = round(r["close"] - CFG.stop_atr_mult * r["atr"], 2)
                    tp = round(r["close"] + CFG.take_profit_atr_mult * r["atr"], 2)
                    tc.submit_order(MarketOrderRequest(
                        symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                        order_class=OrderClass.BRACKET,
                        take_profit=TakeProfitRequest(limit_price=tp),
                        stop_loss=StopLossRequest(stop_price=stop)))
                    log(f"ALIŞ {sym} x{qty} ~${r['close']:.2f} | olasılık {r['prob']:.2f} | stop {stop} | kâr al {tp}")
                    journal([datetime.now(), sym, "AL", qty, r["close"], round(r["prob"], 3), stop, tp, mode])
            elif status == "day_halt":
                log("Günlük zarar limiti doldu: bugün yeni işlem yok.")
                if not getattr(cb, "_halt_sent", None) == today:
                    tg(f"⚠️ Günlük zarar limiti (%{CFG.daily_loss_limit*100:.0f}) doldu. Bugün yeni işlem açılmayacak.")
                    cb._halt_sent = today

            log(f"Özsermaye ${equity:,.2f} | açık pozisyon {len(positions)} | durum {status}")
        except Exception as e:  # ağ hatası vb. botu öldürmesin
            log(f"HATA: {e!r}")
            errors += 1
            if errors in (3, 20):
                tg(f"⚠️ Bot art arda hata alıyor ({errors}): <code>{str(e)[:200]}</code>")
            time.sleep(CFG.bar_minutes * 60)
            continue
        errors = 0
        time.sleep(CFG.bar_minutes * 60)


if __name__ == "__main__":
    main()
