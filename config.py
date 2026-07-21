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
# (zaten elde olanlar + yeni alinanlar toplami bunu gecemez)
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))

# Kompozit skor bu esigin USTUNDE ise ALIM adayi sayilir (varsayilan GUCLU_AL/AL sinirindan
# daha gevsek: 15). Ne kadar dusuk olursa o kadar cok hisse "aday" olur, ama sinyal kalitesi
# de o kadar zayiflar (daha fazla yanlis pozitif riski).
BUY_SCORE_THRESHOLD = float(os.getenv("BUY_SCORE_THRESHOLD", "15"))

# Kompozit skor bu esigin ALTINDA ise elde tutulan pozisyon icin SATIS tetiklenir.
SELL_SCORE_THRESHOLD = float(os.getenv("SELL_SCORE_THRESHOLD", "-20"))

# True iken bot GERÇEK/PAPER EMİR GÖNDERMEZ, sadece ne yapacağını loglar.
# Botu ilk günler DRY_RUN=true ile izlemen önerilir.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# Her pozisyon için ayrılacak yaklaşık dolar tutarı (paper hesapta sanal para)
ALLOCATION_PER_TRADE_USD = float(os.getenv("ALLOCATION_PER_TRADE_USD", "200"))

# Risk yönetimi: stop-loss ve take-profit yüzdeleri
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "3"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "6"))

# Gösterge hesaplamak için geriye dönük kaç günlük veri çekilecek
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "250"))
