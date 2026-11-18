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

    # --- Evren: likit, IEX verisi bol ABD hisse/ETF'leri ---
    symbols: list = field(default_factory=lambda: [
        "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV", "SMH", "ARKK", "TLT", "GLD", "SLV", "USO",
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AMD", "TSLA", "AVGO", "NFLX", "CRM", "ORCL",
        "ADBE", "INTC", "MU", "QCOM", "PLTR", "COIN", "MSTR", "UBER", "SHOP", "PYPL", "JPM", "BAC",
        "WFC", "GS", "C", "XOM", "CVX", "BA", "DIS", "NKE", "WMT", "COST", "KO", "PEP", "MCD", "JNJ",
        "PFE", "MRK", "LLY", "UNH", "V", "MA", "T", "VZ", "SOFI", "RIVN", "F", "GM", "SNAP", "HOOD",
        "MARA", "RIOT",
    ])
    bar_minutes: int = 5           # 5 dakikalık mumlar
    history_days: int = 120        # model eğitimi için geçmiş

    # --- Model / sinyal ---
    horizon_bars: int = 6          # 6 bar (=30 dk) sonrasını tahmin et
    long_threshold: float = 0.35   # yedek eşik; normalde her eğitimde son günlere göre otomatik seçilir
    exit_threshold: float = 0.25   # (backtest için) bunun altına düşerse pozisyonu kapat
    retrain_every_days: int = 1
    stock_cost: float = 0.0005     # hisse: tek yön tahmini maliyet (kayma+spread)
    loss_penalty: float = 0.03     # son 10 günde zarar ettiren sembolün eşiğine eklenir

    # --- Kripto (Alpaca, 7/24) ---
    crypto_symbols: list = field(default_factory=lambda: [
        "BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "LTC/USD", "LINK/USD", "AVAX/USD", "XRP/USD",
        "BCH/USD", "DOT/USD", "UNI/USD", "AAVE/USD", "SHIB/USD",
    ])
    crypto_history_days: int = 60
    crypto_horizon_bars: int = 12  # 1 saat sonrası
    crypto_cost: float = 0.0025    # Alpaca kripto komisyonu (tek yön, alıcı/taker)
    crypto_max_positions: int = 5
    crypto_max_pct: float = 0.08
    crypto_retrain_hours: int = 12

    # --- Risk (deneme hesabı: daha çok işlem, daha geniş limitler) ---
    risk_per_trade: float = 0.004  # işlem başına sermayenin %0.4'ü riske
    max_position_pct: float = 0.10 # tek hissede en fazla %10
    max_open_positions: int = 10
    stop_atr_mult: float = 1.0     # stop = giriş - 1.0*ATR
    take_profit_atr_mult: float = 1.2  # küçük ama sık kâr
    daily_loss_limit: float = 0.05 # gün içi %5 kayıpta o gün yeni işlem yok
    max_drawdown_kill: float = 0.30# zirveden %30 düşüşte bot tamamen durur
    flatten_minutes_before_close: int = 10  # kapanıştan önce hisseleri kapat

    # --- Maliyet varsayımları (backtest) ---
    commission_per_share: float = 0.0
    slippage_bps: float = 2.0      # her işlemde 2 baz puan kayma


CFG = Config()
