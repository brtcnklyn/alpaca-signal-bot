"""Bot ayarları. Anahtarlar .env veya ortam değişkenlerinden okunur, koda yazılmaz."""
import os
from dataclasses import dataclass, field


def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


@dataclass
class Config:
    # --- Alpaca ---
    api_key: str = os.getenv("ALPACA_API_KEY", "")
    secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    # Varsayılan SANAL hesap. Gerçek para için .env'de PAPER=false VE
    # komutta --live-onay vermek gerekir (çift kilit).
    paper: bool = os.getenv("PAPER", "true").lower() != "false"

    # --- Evren: likit, spread'i dar hisse/ETF'ler ---
    symbols: list = field(default_factory=lambda: [
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AMD", "TSLA",
    ])
    bar_minutes: int = 5           # 5 dakikalık mumlar
    history_days: int = 120        # model eğitimi için geçmiş

    # --- Model / sinyal ---
    horizon_bars: int = 6          # 6 bar (=30 dk) sonrasını tahmin et
    long_threshold: float = 0.58   # yükseliş olasılığı bu eşiği geçerse al
    exit_threshold: float = 0.48   # bunun altına düşerse pozisyonu kapat
    retrain_every_days: int = 5

    # --- Risk (en önemli kısım) ---
    risk_per_trade: float = 0.005  # işlem başına sermayenin %0.5'i riske
    max_position_pct: float = 0.15 # tek hissede en fazla %15
    max_open_positions: int = 4
    stop_atr_mult: float = 1.5     # stop = giriş - 1.5*ATR
    take_profit_atr_mult: float = 2.5
    daily_loss_limit: float = 0.02 # gün içi %2 kayıpta bot o gün durur
    max_drawdown_kill: float = 0.10# zirveden %10 düşüşte bot tamamen durur
    flatten_minutes_before_close: int = 10  # kapanıştan önce hepsini kapat

    # --- Maliyet varsayımları (backtest) ---
    commission_per_share: float = 0.0
    slippage_bps: float = 2.0      # her işlemde 2 baz puan kayma


CFG = Config()
