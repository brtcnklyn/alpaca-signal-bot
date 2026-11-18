"""Telegram bildirimleri + gün sonu kâr/zarar raporu.
    python telegram_rapor.py          -> gün sonu raporunu gönderir
    python telegram_rapor.py --test   -> deneme mesajı gönderir
Gerekli: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (ortam değişkeni / GitHub Secret)."""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from config import CFG


def send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("Telegram ayarlı değil (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID), mesaj atlandı.")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20) as r:
            return json.load(r).get("ok", False)
    except Exception as e:
        print(f"Telegram hatası: {e!r}")
        return False


def _usd(x):
    return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"


def daily_report(title: str = "Gün Sonu Raporu", extra=None) -> str:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest

    tc = TradingClient(CFG.api_key, CFG.secret_key, paper=CFG.paper)
    acct = tc.get_account()
    eq, prev = float(acct.equity), float(acct.last_equity)
    day_pnl = eq - prev
    day_pct = day_pnl / prev if prev else 0

    # Bugün dolan emirler -> sembol bazında gerçekleşen k/z (FIFO yaklaşık)
    since = datetime.now(timezone.utc) - timedelta(hours=18)
    orders = tc.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=since, limit=500, nested=True))
    fills = []
    def walk(o):
        if o.filled_at and float(o.filled_qty or 0) > 0:
            fills.append(o)
        for leg in (o.legs or []):
            walk(leg)
    for o in orders:
        walk(o)
    fills.sort(key=lambda o: o.filled_at)
    per_sym, buys, sells = {}, 0, 0
    lots = {}
    for o in fills:
        q, px, s = float(o.filled_qty), float(o.filled_avg_price), o.symbol
        if o.side.value == "buy":
            buys += 1
            lots.setdefault(s, []).append([q, px])
        else:
            sells += 1
            rem = q
            while rem > 0 and lots.get(s):
                lq, lpx = lots[s][0]
                take = min(rem, lq)
                per_sym[s] = per_sym.get(s, 0) + take * (px - lpx)
                rem -= take
                lots[s][0][0] -= take
                if lots[s][0][0] <= 1e-9:
                    lots[s].pop(0)
    wins = sum(1 for v in per_sym.values() if v > 0)

    # Haftalık / aylık
    lines_hist = []
    try:
        ph = tc.get_portfolio_history(GetPortfolioHistoryRequest(period="1M", timeframe="1D"))
        vals = [v for v in ph.equity if v]
        if len(vals) >= 6:
            lines_hist.append(f"Son 5 gün: {(eq / vals[-6] - 1):+.2%}")
        if vals:
            lines_hist.append(f"Son 1 ay:  {(eq / vals[0] - 1):+.2%}")
    except Exception:
        pass

    positions = tc.get_all_positions()
    mode = "🧪 SANAL" if CFG.paper else "💵 GERÇEK"
    icon = "🟢" if day_pnl >= 0 else "🔴"
    out = [
        f"<b>{icon} {title}</b> — {datetime.now(timezone.utc):%d.%m.%Y} ({mode})",
        "",
        f"<b>Günlük K/Z:</b> {_usd(day_pnl)} ({day_pct:+.2%})",
        f"<b>Özsermaye:</b> ${eq:,.2f}",
        *lines_hist,
        "",
        f"<b>İşlemler:</b> {buys} alış, {sells} satış",
    ]
    if per_sym:
        out.append(f"Kapanan: {len(per_sym)} hisse, {wins} kârlı")
        for s, v in sorted(per_sym.items(), key=lambda kv: -kv[1]):
            out.append(f"  • {s}: {_usd(v)}")
    if positions:
        out.append("")
        out.append(f"<b>Açık pozisyon ({len(positions)}):</b>")
        for p in positions:
            out.append(f"  • {p.symbol} x{p.qty}: {_usd(float(p.unrealized_pl))}")
    else:
        out.append("Açık pozisyon yok ✅")
    if extra:
        out.append("")
        out.extend(extra)
    return "\n".join(out)


if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = send("✅ Borsa botu Telegram bağlantısı çalışıyor.")
        sys.exit(0 if ok else 1)
    if "--ara" in sys.argv:
        msg = daily_report(title="Anlık Durum Raporu", extra=["(Elle istenen ara rapor)"])
    else:
        msg = daily_report()
    print(msg)
    send(msg)
