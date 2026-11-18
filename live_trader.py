"""ABD hisse botu (canlı döngü). Varsayılan: Alpaca SANAL (paper) hesap.
Gerçek para için: .env içinde PAPER=false  VE  python live_trader.py --live-onay
Her 5 dakikada: veri çek -> özellik -> tahmin -> risk kontrol -> braket emir (stop + kâr al).
Kendini ayarlama: her eğitimde alım eşiğini son günlerde en çok kazandıran değere çeker,
zarar ettiren sembollerin eşiğini yükseltir (learn.py)."""
import argparse
import csv
import sys
import time
from datetime import datetime

import pandas as pd

from telegram_rapor import send as tg

import learn
import model as M
from config import CFG
from data import fetch_bars
from features import FEATURES, add_label, build_features
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


def asset_class(p) -> str:
    return getattr(p.asset_class, "value", str(p.asset_class))


def latest_probs(clf, feats, now, max_age_min):
    """Her sembolün son barı; bayat (IEX'te seyrek) olanlar elenir."""
    last = feats.groupby(level="symbol").tail(1)
    ts = last.index.get_level_values("timestamp")
    fresh = ts >= pd.Timestamp(now).tz_convert(ts.tz) - pd.Timedelta(minutes=max_age_min)
    latest = last[fresh].dropna(subset=FEATURES).droplevel("timestamp")
    if len(latest):
        latest["prob"] = clf.predict_proba(latest[FEATURES])[:, 1]
    else:
        latest["prob"] = []
    return latest


def fmt_tune(th, info):
    if not info:
        return f"eşik {th:.2f}"
    mod = "🔍 KEŞİF MODU (kârlı dilim bulunamadı, öğrenmek için deniyor) " if info.get("kesif") else ""
    return (f"{mod}eşik {th:.2f} = en güçlü %{info['top']*100:g} sinyal (son 5 günde bu eşikle {info['n']} sinyal, "
            f"ort. {info['mean']*100:+.3f}% maliyet sonrası, isabet %{info['win']*100:.0f})")


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
    log(f"Hisse botu başladı | mod={mode} | özsermaye=${float(acct.equity):,.2f} | {len(CFG.symbols)} sembol")

    clf, last_train = None, None
    th, penalties = CFG.long_threshold, {}
    exit_level = 0.0
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
    scans, mid_sent, session_min = 0, None, None

    while True:
        if args.max_dakika and (time.time() - started) / 60 >= args.max_dakika:
            log("Süre sınırı doldu, çıkılıyor (pozisyonlar stop/kâr-al emirleriyle korunuyor).")
            return
        try:
            clock = tc.get_clock()
            if not clock.is_open:
                wait = (clock.next_open - clock.timestamp).total_seconds()
                # Bu çalıştırmanın süresi içinde açılış yoksa bekleme, çık (bir sonraki tetikleme yakalar)
                if args.max_dakika and wait > 5 * 3600:
                    log(f"Açılışa {wait / 3600:.1f} saat var, bu çalıştırma bekleyemez; çıkılıyor.")
                    return
                log(f"Piyasa kapalı. {wait / 3600:.1f} saat sonra açılış.")
                time.sleep(min(max(wait, 60), 1800))
                continue

            today = clock.timestamp.date()
            if clf is None or last_train is None or (today - last_train).days >= CFG.retrain_every_days:
                log("Model eğitiliyor (son günlerin verisiyle)...")
                hist = add_label(build_features(fetch_bars(CFG.symbols)), CFG.horizon_bars, cost=CFG.stock_cost)
                tuned, info = M.tune_threshold(hist, CFG.stock_cost)
                th = tuned if tuned is not None else CFG.long_threshold
                exit_level = info["exit"] if info else th * 0.7
                clf = M.train(hist)
                M.save(clf)
                last_train = today
                penalties = learn.symbol_penalties(tc)
                log(f"Kendini ayarlama: {fmt_tune(th, info)} | cezalı semboller: {penalties or 'yok'}")
                pen_txt = ", ".join(f"{s} +{v:.2f}" for s, v in penalties.items()) or "yok"
                tg(f"📈 <b>Hisse botu seansta</b> ({mode}), {hist.index.get_level_values('symbol').nunique()} "
                   f"sembol taranıyor. Özsermaye ${float(tc.get_account().equity):,.2f}\n"
                   f"Bugünkü {fmt_tune(th, info)}\nZarar ettirdiği için eşiği yükseltilenler: {pen_txt}")

            acct = tc.get_account()
            equity = float(acct.equity)
            if acct.trading_blocked or acct.account_blocked:
                log("Hesap işlem için bloke. Bekleniyor.")
                time.sleep(300)
                continue
            if today != current_day:
                current_day = today
                cb.new_day(float(acct.last_equity))
                scans, session_min = 0, None
                try:  # bugünkü seans uzunluğu (erken kapanış günleri için)
                    from alpaca.trading.requests import GetCalendarRequest
                    cal = tc.get_calendar(GetCalendarRequest(start=today, end=today))[0]
                    session_min = (cal.close - cal.open).total_seconds() / 60
                except Exception as e:
                    log(f"Takvim alınamadı: {e!r}")
            status = cb.check(equity)

            mins_to_close = (clock.next_close - clock.timestamp).total_seconds() / 60
            # Sadece hisse pozisyonları (kripto botu kendi pozisyonlarını yönetir)
            positions = {p.symbol: p for p in tc.get_all_positions() if asset_class(p) == "us_equity"}

            if status == "kill":
                log("MAKS DÜŞÜŞ - BOT DURDU: tüm pozisyonlar kapatılıyor")
                tc.close_all_positions(cancel_orders=True)
                tg(f"🛑 <b>BOT DURDU</b>: zirveden %{CFG.max_drawdown_kill*100:.0f} düşüş limiti aşıldı. "
                   f"Tüm pozisyonlar kapatıldı. Özsermaye ${equity:,.2f}")
                sys.exit("Maksimum düşüş limiti aşıldı. Bot durdu; stratejiyi gözden geçir.")

            # Gün sonu: hisseleri kapat
            if mins_to_close <= CFG.flatten_minutes_before_close:
                if positions:
                    log("Gün sonu: hisse pozisyonları kapatılıyor")
                    for o in tc.get_orders():
                        if learn.norm(o.symbol) in positions:
                            tc.cancel_order_by_id(o.id)
                    time.sleep(2)
                    for sym in positions:
                        try:
                            tc.close_position(sym)
                        except Exception as e:
                            log(f"{sym} kapatılamadı: {e!r}")
                time.sleep(60)
                continue

            # Tahmin
            feats = build_features(fetch_bars(CFG.symbols, days=7))
            latest = latest_probs(clf, feats, clock.timestamp, max_age_min=45)
            exit_th = exit_level

            # Çıkışlar
            for sym, p in positions.items():
                if sym in latest.index and latest.loc[sym, "prob"] < exit_th:
                    log(f"ÇIKIŞ sinyali {sym} (olasılık {latest.loc[sym, 'prob']:.2f})")
                    for o in tc.get_orders():
                        if o.symbol == sym:
                            tc.cancel_order_by_id(o.id)
                    time.sleep(1)
                    tc.close_position(sym)
                    journal([datetime.now(), sym, "SAT", p.qty, latest.loc[sym, "close"],
                             round(latest.loc[sym, "prob"], 3), "", "", mode])

            # Girişler
            if status == "ok" and len(latest):
                open_orders = {o.symbol for o in tc.get_orders()}
                slots = CFG.max_open_positions - len(positions)
                need = th + latest.index.map(lambda s: penalties.get(s, 0.0)).to_numpy()
                cands = latest[(latest["prob"] > need)
                               & ~latest.index.isin(list(positions) + list(open_orders))]
                for sym, r in cands.sort_values("prob", ascending=False).head(max(0, slots)).iterrows():
                    qty = position_size(equity, r["close"], r["atr"])
                    qty = min(qty, int(float(acct.buying_power) // r["close"]))
                    if qty <= 0:
                        continue
                    stop = round(r["close"] - CFG.stop_atr_mult * r["atr"], 2)
                    tp = round(r["close"] + CFG.take_profit_atr_mult * r["atr"], 2)
                    try:
                        tc.submit_order(MarketOrderRequest(
                            symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                            order_class=OrderClass.BRACKET,
                            take_profit=TakeProfitRequest(limit_price=tp),
                            stop_loss=StopLossRequest(stop_price=stop)))
                    except Exception as e:
                        log(f"{sym} emri reddedildi: {e!r}")
                        continue
                    log(f"ALIŞ {sym} x{qty} ~${r['close']:.2f} | olasılık {r['prob']:.2f} | stop {stop} | kâr al {tp}")
                    journal([datetime.now(), sym, "AL", qty, r["close"], round(r["prob"], 3), stop, tp, mode])
            elif status == "day_halt":
                log("Günlük zarar limiti doldu: bugün yeni işlem yok.")
                if not getattr(cb, "_halt_sent", None) == today:
                    tg(f"⚠️ Günlük zarar limiti (%{CFG.daily_loss_limit*100:.0f}) doldu. Bugün yeni işlem açılmayacak.")
                    cb._halt_sent = today

            scans += 1
            if scans % 6 == 0:  # yarım saatte bir: bugünkü zararlardan da öğren
                penalties = learn.symbol_penalties(tc)
            # Gün ortası raporu: seansın yarısında bir kez (yeniden başlatmada tekrar atmasın diye 30 dk pencere)
            half = (session_min or 390) / 2
            if mid_sent != today and half - 30 < mins_to_close <= half:
                mid_sent = today
                try:
                    from telegram_rapor import daily_report
                    top = latest.sort_values("prob", ascending=False).head(3)
                    extra = [f"<b>Bot çalışıyor</b> ✅ Bu çalıştırmada {scans} tarama, {len(latest)} sembol.",
                             f"Alım eşiği {th:.2f} | şu an en yüksek: "
                             + ", ".join(f"{s} {p:.2f}" for s, p in top["prob"].items())]
                    tg(daily_report(title="Gün Ortası Raporu", extra=extra))
                except Exception as e:
                    log(f"Gün ortası raporu gönderilemedi: {e!r}")

            top1 = latest["prob"].max() if len(latest) else float("nan")
            log(f"Özsermaye ${equity:,.2f} | açık hisse {len(positions)} | eşik {th:.2f} | "
                f"en yüksek olasılık {top1:.2f} | durum {status}")
        except Exception as e:  # ağ hatası vb. botu öldürmesin
            log(f"HATA: {e!r}")
            errors += 1
            if errors in (3, 20):
                tg(f"⚠️ Hisse botu art arda hata alıyor ({errors}): <code>{str(e)[:200]}</code>")
            time.sleep(CFG.bar_minutes * 60)
            continue
        errors = 0
        time.sleep(CFG.bar_minutes * 60)


if __name__ == "__main__":
    main()
