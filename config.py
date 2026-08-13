import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

# Virgülle ayrılmış hisse listesi, örn: "AAPL,MSFT,NVDA"
# AUTO_SELECT=true iken bu liste yalnizca "elde tut / izlemeye devam et" icin yedek olarak kullanilir,
# yeni alimlar universe.py taramasindan gelir.
TICKERS = [t.strip().upper() for t in os.getenv("TICKERS", "AAPL").split(",") if t.strip()]

# True ise: bot her calistiginda universe.py listesini tarar, en guclu AL sinyali veren
# TOP_N hisseyi kendi secer. False ise: sadece yukaridaki TICKERS listesine bakar.
AUTO_SELECT = os.getenv("AUTO_SELECT", "false").lower() == "true"

# AUTO_SELECT=true iken ayni anda en fazla kac YENI pozisyon acilabilir
TOP_N = int(os.getenv("TOP_N", "3"))

# AUTO_SELECT=true iken ayni anda toplamda en fazla kac ACIK pozisyon olabilir
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "10"))

# Kompozit skor bu esigin USTUNDE ise ALIM adayi sayilir.
BUY_SCORE_THRESHOLD = float(os.getenv("BUY_SCORE_THRESHOLD", "15"))

# Kompozit skor bu esigin ALTINDA ise elde tutulan pozisyon icin SATIS tetiklenir.
SELL_SCORE_THRESHOLD = float(os.getenv("SELL_SCORE_THRESHOLD", "-20"))

# 0'dan buyukse: bu fiyatin USTUNDEKI hisseler alim adayi olarak degerlendirilmez.
# Kucuk sermayeyle en az 1 adet alabilmek icin kullanilir. 0 = filtre yok.
MAX_STOCK_PRICE = float(os.getenv("MAX_STOCK_PRICE", "0"))

# True iken bot GERÇEK/PAPER EMİR GÖNDERMEZ, sadece ne yapacağını loglar.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# Her pozisyon için ayrılacak yaklaşık dolar tutarı
ALLOCATION_PER_TRADE_USD = float(os.getenv("ALLOCATION_PER_TRADE_USD", "10000"))

# --- Risk yönetimi ---
# ATR (volatilite) tabanlı stop/hedef kullanilsin mi? Turtle Traders ve pek cok
# kurumsal trend-takip sisteminin kullandigi yontem: sabit yuzde yerine hissenin
# kendi gunluk oynakligina gore stop mesafesi belirler.
USE_ATR_STOPS = os.getenv("USE_ATR_STOPS", "true").lower() == "true"
ATR_STOP_MULT = float(os.getenv("ATR_STOP_MULT", "2.0"))     # stop = giris - 2*ATR
ATR_TARGET_MULT = float(os.getenv("ATR_TARGET_MULT", "4.0")) # hedef = giris + 4*ATR (2:1 kazanc/risk)

# ATR verisi yoksa (yetersiz gecmis) bu sabit yuzdelere geri duser
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "3"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "6"))

# Ana trend filtresi: fiyat SMA200'un altindaysa (uzun vadeli dusus trendi) ALIM
# sinyalleri bastirilir. "The trend is your friend" - Ed Seykota, Paul Tudor Jones
# ve pek cok trend-takip sisteminin temel prensibi.
TREND_FILTER_ENABLED = os.getenv("TREND_FILTER_ENABLED", "true").lower() == "true"

# Gösterge hesaplamak için geriye dönük kaç günlük veri çekilecek
# (SMA200 + ATR/MACD seed payi icin >=260 onerilir)
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "330"))
