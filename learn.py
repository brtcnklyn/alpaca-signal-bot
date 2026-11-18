"""Hatalardan öğrenme: hesabın gerçekleşen işlemlerinden sembol bazında kâr/zarar çıkarır.
Son günlerde zarar ettiren sembollerin alım eşiği yükseltilir (o hatayı tekrar etmemek için),
kâr ettirenlerin cezası kalkar. Model de her eğitimde en yeni veriyle yeniden öğrenir."""
from datetime import datetime, timedelta, timezone

from config import CFG


def norm(sym: str) -> str:
    """'BTC/USD' ve 'BTCUSD' aynı sembol sayılsın."""
    return sym.replace("/", "")


def trade_stats(tc, days: int = 10) -> dict:
    """{sembol: {"n": kapanan işlem, "pnl": toplam $, "wins": kârlı işlem}} (FIFO)."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    since = datetime.now(timezone.utc) - timedelta(days=days)
    orders = tc.get_orders(GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=since,
                                            limit=500, nested=True))
    fills = []

    def walk(o):
        if o.filled_at and float(o.filled_qty or 0) > 0:
            fills.append(o)
        for leg in (o.legs or []):
            walk(leg)

    for o in orders:
        walk(o)
    fills.sort(key=lambda o: o.filled_at)
    lots, stats = {}, {}
    for o in fills:
        s, q, px = norm(o.symbol), float(o.filled_qty), float(o.filled_avg_price)
        if o.side.value == "buy":
            lots.setdefault(s, []).append([q, px])
            continue
        rem, pnl = q, 0.0
        while rem > 1e-12 and lots.get(s):
            lq, lpx = lots[s][0]
            take = min(rem, lq)
            pnl += take * (px - lpx)
            rem -= take
            lots[s][0][0] -= take
            if lots[s][0][0] <= 1e-12:
                lots[s].pop(0)
        if rem < q:  # en az kısmen eşleşen bir alış vardı
            st = stats.setdefault(s, {"n": 0, "pnl": 0.0, "wins": 0})
            st["n"] += 1
            st["pnl"] += pnl
            st["wins"] += pnl > 0
    return stats


def symbol_penalties(tc, days: int = 10) -> dict:
    """{sembol: eşiğe eklenecek ceza}. Zarar ettiren sembol daha emin olmadan alınmaz."""
    try:
        stats = trade_stats(tc, days)
    except Exception as e:
        print(f"İşlem geçmişi okunamadı: {e!r}")
        return {}
    out = {}
    for s, st in stats.items():
        if st["n"] >= 2 and st["pnl"] < 0:
            k = 2 if st["n"] >= 4 and st["wins"] / st["n"] < 0.3 else 1
            out[s] = CFG.loss_penalty * k
    return out
