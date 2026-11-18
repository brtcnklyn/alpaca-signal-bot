"""Kripto botu: Alpaca SANAL hesapta 7/24 BTC, ETH, SOL vb. Aynı LightGBM yaklaşımı.
Kripto için braket emir yok: stop / kâr al her 5 dakikada yazılımla kontrol edilir.
Komisyon (tek yön ~%0.25) etiketlerde ve eşik ayarında hesaba katılır."""
import argparse
import sys
import time
from datetime import datetime, timezone

from telegram_rapor import send as tg

import learn
import model as M
from config import CFG
from data import fetch_crypto_bars
from features import add_label, build_features
from live_trader import asset_class, fmt_tune, journal, latest_probs, log
from risk import CircuitBreaker


def train_all(syms):
    hist = add_label(build_features(fetch_crypto_bars(syms, CFG.crypto_history_days), session="24h"),
                     CFG.crypto_horizon_bars, cost=CFG.crypto_cost)
    th, info = M.tune_threshold(hist, CFG.crypto_cost, val_days=7, min_trades=20)
    clf = M.train(hist)
    return clf, (th if th is not None else CFG.long_threshold), info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-onay", action="store_true")
    ap.add_argument("--max-dakika", type=int, default=0)
    args = ap.parse_args()
    if not CFG.api_key:
        sys.exit("ALPACA_API_KEY yok.")
    if not CFG.paper and not args.live_onay:
        sys.exit("PAPER=false ama --live-onay verilmedi.")

    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, OrderSide, TimeInForce
    from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest

    tc = TradingClient(CFG.api_key, CFG.secret_key, paper=CFG.paper)
    mode = "SANAL" if CFG.paper else "GERCEK PARA"
    tradable = {a.symbol for a in tc.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO))
                if a.tradable}
    syms = [s for s in CFG.crypto_symbols if s in tradable]
    by_norm = {learn.norm(s): s for s in syms}
    acct = tc.get_account()
    log(f"Kripto botu başladı | mod={mode} | {len(syms)} coin: {', '.join(syms)}")

    cb = CircuitBreaker(float(acct.equity))
    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        ph = tc.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
        cb.peak = max([v for v in ph.equity if v] + [float(acct.equity)])
    except Exception as e:
        log(f"Portföy geçmişi alınamadı: {e!r}")
    cb.new_day(float(acct.last_equity))

    started = time.time()
    clf, th, trained_at, penalties = None, CFG.long_threshold, 0.0, {}
    exit_level = 0.0
    errors, loops, day = 0, 0, None

    while True:
        if args.max_dakika and (time.time() - started) / 60 >= args.max_dakika:
            log("Süre sınırı doldu, çıkılıyor (zincir yeniden başlatır).")
            return
        try:
            if clf is None or time.time() - trained_at > CFG.crypto_retrain_hours * 3600:
                log("Kripto modeli eğitiliyor...")
                clf, th, info = train_all(syms)
                trained_at = time.time()
                exit_level = info["exit"] if info else th * 0.7
                penalties = learn.symbol_penalties(tc)
                log(f"Kendini ayarlama: {fmt_tune(th, info)} | cezalı: {penalties or 'yok'}")
                pen_txt = ", ".join(f"{s} +{v:.2f}" for s, v in penalties.items() if s in by_norm) or "yok"
                tg(f"🪙 <b>Kripto botu çalışıyor</b> ({mode}), {len(syms)} coin, 7/24.\n"
                   f"{fmt_tune(th, info).replace('son 5 gün', 'son 7 gün')}\n"
                   f"Zarar ettirdiği için eşiği yükseltilenler: {pen_txt}")

            acct = tc.get_account()
            equity = float(acct.equity)
            today = datetime.now(timezone.utc).date()
            if today != day:
                day = today
                cb.new_day(float(acct.last_equity))
            status = cb.check(equity)
            if status == "kill":
                tc.close_all_positions(cancel_orders=True)
                tg(f"🛑 <b>BOT DURDU</b> (kripto): zirveden %{CFG.max_drawdown_kill*100:.0f} düşüş. Özsermaye ${equity:,.2f}")
                sys.exit("Maksimum düşüş limiti aşıldı.")

            positions = {p.symbol: p for p in tc.get_all_positions() if asset_class(p) == "crypto"}
            feats = build_features(fetch_crypto_bars(syms, days=4), session="24h")
            latest = latest_probs(clf, feats, datetime.now(timezone.utc), max_age_min=30)
            latest.index = [learn.norm(s) for s in latest.index]
            exit_th = exit_level

            # Çıkışlar: stop / kâr al / sinyal zayıfladı
            for psym, p in positions.items():
                if psym not in latest.index:
                    continue
                r = latest.loc[psym]
                entry, price = float(p.avg_entry_price), float(p.current_price)
                why = None
                if price <= entry - CFG.stop_atr_mult * r["atr"]:
                    why = "stop"
                elif price >= entry + CFG.take_profit_atr_mult * r["atr"]:
                    why = "kar_al"
                elif r["prob"] < exit_th:
                    why = "sinyal"
                if why:
                    tc.close_position(psym)
                    log(f"SATIŞ {psym} ({why}) giriş {entry:.6g} -> {price:.6g} | k/z ${float(p.unrealized_pl):+,.2f}")
                    journal([datetime.now(), psym, f"SAT-{why}", p.qty, price, round(r["prob"], 3), "", "", mode])

            # Girişler
            if status == "ok" and len(latest):
                slots = CFG.crypto_max_positions - len(positions)
                need = th + latest.index.map(lambda s: penalties.get(s, 0.0)).to_numpy()
                cands = latest[(latest["prob"] > need) & ~latest.index.isin(list(positions))]
                cash = float(acct.non_marginable_buying_power or acct.cash)
                for nsym, r in cands.sort_values("prob", ascending=False).head(max(0, slots)).iterrows():
                    stop_pct = CFG.stop_atr_mult * r["atr"] / r["close"]
                    notional = min(equity * CFG.risk_per_trade / max(stop_pct, 1e-4),
                                   equity * CFG.crypto_max_pct, cash * 0.95)
                    if notional < 10:
                        continue
                    try:
                        tc.submit_order(MarketOrderRequest(symbol=by_norm[nsym], notional=round(notional, 2),
                                                           side=OrderSide.BUY, time_in_force=TimeInForce.GTC))
                    except Exception as e:
                        log(f"{nsym} emri reddedildi: {e!r}")
                        continue
                    cash -= notional
                    log(f"ALIŞ {nsym} ${notional:,.0f} ~{r['close']:.6g} | olasılık {r['prob']:.2f}")
                    journal([datetime.now(), nsym, "AL", round(notional, 2), r["close"], round(r["prob"], 3),
                             round(r["close"] * (1 - stop_pct), 6),
                             round(r["close"] + CFG.take_profit_atr_mult * r["atr"], 6), mode])

            loops += 1
            if loops % 6 == 0:
                penalties = learn.symbol_penalties(tc)
            top1 = latest["prob"].max() if len(latest) else float("nan")
            log(f"Özsermaye ${equity:,.2f} | açık kripto {len(positions)} | eşik {th:.2f} | "
                f"en yüksek olasılık {top1:.2f} | durum {status}")
        except Exception as e:
            log(f"HATA: {e!r}")
            errors += 1
            if errors in (3, 20):
                tg(f"⚠️ Kripto botu art arda hata alıyor ({errors}): <code>{str(e)[:200]}</code>")
            time.sleep(CFG.bar_minutes * 60)
            continue
        errors = 0
        time.sleep(CFG.bar_minutes * 60)


if __name__ == "__main__":
    main()
