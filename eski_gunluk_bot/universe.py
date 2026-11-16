"""
universe.py
Bot'un otomatik hisse seçimi yaparken tarayacağı likit, büyük hacimli
NASDAQ/NYSE hisselerinin listesi. İstersen bu listeyi kendi ilgi alanına
göre kısaltıp uzatabilirsin - ne kadar uzun olursa tarama o kadar sürer
(her hisse için bir veri isteği gider).
"""

UNIVERSE = [
    # Teknoloji
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "ORCL", "CRM",
    "ADBE", "AMD", "INTC", "CSCO", "QCOM", "TXN", "NOW", "INTU", "IBM", "UBER",
    # Finans
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP",
    # Sağlık
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK",
    # Tüketici
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "PG", "KO", "PEP",
    # Enerji / Sanayi
    "XOM", "CVX", "CAT", "BA", "GE",
    # ETF (opsiyonel, genel piyasa yönü için)
    "SPY", "QQQ",
    # Genellikle dusuk fiyatli, likit buyuk/orta olcekli hisseler
    # (fiyatlar zamanla degisir, MAX_STOCK_PRICE filtresi asil filtreyi anlik fiyata gore yapar)
    "F", "T", "BAC", "WFC", "PFE", "KO", "CSCO", "INTC", "SOFI", "PLTR",
    "NIO", "RIVN", "LCID", "SNAP", "PARA", "WBD", "VALE", "ITUB", "UBER", "GRAB",
    "AAL", "CCL", "NCLH", "KMI", "NU", "PBR", "GOLD", "M", "GAP", "KSS",
]
