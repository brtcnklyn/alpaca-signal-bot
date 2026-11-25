"""Nöbetçi: GitHub Actions'ta 7/24 zincir halinde çalışır (GitHub'ın zamanlayıcısı güvenilmez olduğu için).
Her 5 dakikada saate bakar ve gerektiğinde trend botunu çalıştırır:
  - Hisse : ABD seansı açılmadan en fazla 90 dk önce (ya da kaçırıldıysa seans içinde) günde bir kez
  - Kripto: her gün 00:10 UTC'den sonra bir kez
  - Gün sonu raporu: hafta içi kapanıştan 20 dk sonra bir kez
Yeniden başlatılırsa o günün işini tekrar dener; emirler tarih+sembol kimliğiyle gönderildiği için çift emir olmaz."""
import argparse
import sys
import time
from datetime import datetime, timezone

from config import CFG
from telegram_rapor import daily_report, send
from trend_trader import log, run_crypto, run_stocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-dakika", type=int, default=330)
    ap.add_argument("--durum", default="", help="zincirden gelen 'hisse=YYYY-MM-DD;kripto=...;rapor=...'")
    args = ap.parse_args()
    if not CFG.paper:
        sys.exit("Yalnızca SANAL hesap (PAPER=true).")
    from alpaca.trading.client import TradingClient

    tc = TradingClient(CFG.api_key, CFG.secret_key, paper=True)
    log("Nöbetçi başladı")
    started = time.time()
    done = {"hisse": None, "kripto": None, "rapor": None}
    for part in filter(None, args.durum.split(";")):  # önceki çalıştırmanın yaptıkları
        k, _, v = part.partition("=")
        if k in done and v:
            done[k] = datetime.strptime(v, "%Y-%m-%d").date()
    log(f"Önceki durum: {done}")
    errors = 0
    while (time.time() - started) / 60 < args.max_dakika:
        try:
            now = datetime.now(timezone.utc)
            clock = tc.get_clock()
            # Hisse
            target = clock.timestamp.date() if clock.is_open else clock.next_open.date()
            to_open = (clock.next_open - clock.timestamp).total_seconds() / 60
            to_close = (clock.next_close - clock.timestamp).total_seconds() / 60
            if done["hisse"] != target and ((not clock.is_open and to_open <= 90)
                                            or (clock.is_open and to_close > 30)):
                log(f"Hisse trend kontrolü ({target})")
                send(run_stocks(tc))
                done["hisse"] = target
            # Kripto
            if done["kripto"] != now.date() and (now.hour, now.minute) >= (0, 10):
                log(f"Kripto trend kontrolü ({now.date()})")
                send(run_crypto(tc))
                done["kripto"] = now.date()
            # Gün sonu raporu: hafta içi 21:20 UTC sonrası (kış kapanışı 21:00, yaz 20:00)
            if (not clock.is_open and done["rapor"] != now.date() and now.weekday() < 5
                    and now.hour * 60 + now.minute >= 21 * 60 + 20):
                send(daily_report())
                done["rapor"] = now.date()
            errors = 0
        except Exception as e:
            errors += 1
            log(f"HATA: {e!r}")
            if errors in (3, 20):
                send(f"⚠️ Trend botu art arda hata alıyor ({errors}): <code>{str(e)[:200]}</code>")
        time.sleep(300)
    log("Süre doldu, zincir yeniden başlatacak.")
    with open(".nobetci_durum", "w") as fh:
        fh.write(";".join(f"{k}={v}" for k, v in done.items() if v))


if __name__ == "__main__":
    main()
