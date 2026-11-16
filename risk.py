"""Risk motoru: pozisyon boyutu ve devre kesiciler. Hem backtest hem canlıda aynı kurallar."""
import math

from config import CFG


def position_size(equity: float, price: float, atr: float, cfg=CFG) -> int:
    """Stop mesafesine göre boyut: stop olursa en fazla equity*risk_per_trade kaybedilir."""
    if atr <= 0 or price <= 0:
        return 0
    stop_dist = cfg.stop_atr_mult * atr
    by_risk = equity * cfg.risk_per_trade / stop_dist
    by_cap = equity * cfg.max_position_pct / price
    return max(0, math.floor(min(by_risk, by_cap)))


class CircuitBreaker:
    def __init__(self, start_equity: float, cfg=CFG):
        self.cfg = cfg
        self.peak = start_equity
        self.day_start = start_equity
        self.killed = False

    def new_day(self, equity: float):
        self.day_start = equity

    def check(self, equity: float) -> str:
        """'ok', 'day_halt' (bugün yeni işlem yok) veya 'kill' (bot durur)."""
        self.peak = max(self.peak, equity)
        if self.killed or equity <= self.peak * (1 - self.cfg.max_drawdown_kill):
            self.killed = True
            return "kill"
        if equity <= self.day_start * (1 - self.cfg.daily_loss_limit):
            return "day_halt"
        return "ok"
