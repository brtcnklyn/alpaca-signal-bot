# Signal Bot — Alpaca Paper Trading

Bu bot, günlük kapanış verisine dayalı teknik göstergelerle (SMA, RSI, MACD, Bollinger)
Alpaca **paper trading** (sanal para) hesabında otomatik alım/satım yapar.

**Bu bir yatırım tavsiyesi aracı değildir.** Sinyaller geçmiş fiyat verisine dayalı
olasılık tahminleridir, garanti değildir. Gerçek parayla kullanmadan önce haftalarca
paper hesapta izle.

---

## 1. Alpaca hesabı ve API anahtarı

1. https://alpaca.markets adresinden ücretsiz kayıt ol.
2. Giriş yaptıktan sonra sağ üstten **Paper Trading** moduna geç (varsayılan zaten budur).
3. Dashboard'da **"API Keys"** bölümünden yeni bir **Paper** API key + secret oluştur.
   Secret sadece bir kez gösterilir, kaydet.

## 2. Python kurulumu (yapmadıysan)

- Windows: https://www.python.org/downloads/ üzerinden Python 3.11+ indir, kurarken
  **"Add python.exe to PATH"** kutusunu işaretle.
- Mac: Terminal'de `python3 --version` yaz, yoksa https://www.python.org/downloads/macos/
  üzerinden kur (veya `brew install python`).

## 3. Proje klasörünü hazırlama

Bu klasördeki tüm dosyaları bilgisayarında bir klasöre koy (örn. `Belgeler/alpaca-signal-bot`).
Terminal / Komut İstemi'ni o klasörde aç:

```bash
cd alpaca-signal-bot
python -m venv venv
```

Sanal ortamı etkinleştir:
- Windows (PowerShell): `venv\Scripts\Activate.ps1`
- Mac/Linux: `source venv/bin/activate`

Bağımlılıkları yükle:

```bash
pip install -r requirements.txt
```

## 4. Ayarları girme

`.env.example` dosyasını `.env` olarak kopyala ve içine kendi Alpaca **paper** API
anahtarlarını yapıştır:

```bash
cp .env.example .env      # Mac/Linux
copy .env.example .env    # Windows
```

`.env` dosyasını bir metin editörüyle açıp:
- `ALPACA_API_KEY` ve `ALPACA_SECRET_KEY` — Alpaca'dan aldığın paper anahtarlar
- `TICKERS` — `AUTO_SELECT=false` iken takip edilecek sabit hisse listesi
- `DRY_RUN` — `true` iken bot emir göndermez, sadece ne yapacağını loglar
- `ALLOCATION_PER_TRADE_USD` — her pozisyon için ayrılacak sanal dolar tutarı
- `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT` — otomatik zarar-kes / kâr-al yüzdeleri
- `AUTO_SELECT=true` — bot, `universe.py` içindeki ~45 likit NASDAQ/NYSE hissesini
  kendi tarar, en güçlü AL sinyali verenlerden en fazla `TOP_N` tanesini seçip alır.
  `TICKERS` listesi bu modda yalnızca yedek olarak durur, kullanılmaz.
- `TOP_N` — `AUTO_SELECT` modunda tek seferde açılabilecek yeni pozisyon sayısı
- `MAX_OPEN_POSITIONS` — aynı anda açık olabilecek toplam pozisyon sayısı (elde
  olanlar dahil). Bu sayı dolduğunda bot yeni alım yapmaz, sadece elde olanları
  satış sinyaline göre izlemeye devam eder.
- `BUY_SCORE_THRESHOLD` (varsayılan 15) — kompozit skor bu değerin üstündeyse hisse
  alım adayı sayılır. Düşürürsen daha çok aday bulunur ama sinyal kalitesi zayıflar
  (daha fazla "yanlış pozitif" riski) — bu bir denge tercihi, garanti artış değil.
- `SELL_SCORE_THRESHOLD` (varsayılan -20) — elde tutulan bir pozisyon için kompozit
  skor bu değerin altına inerse satış tetiklenir.
- `MAX_STOCK_PRICE` (varsayılan 50) — bu fiyatın üstündeki hisseler alım adayı
  sayılmaz. Küçük `ALLOCATION_PER_TRADE_USD` ile en az 1 adet alabilmek için
  kullanılır. 0 = filtre yok.

**Not:** Elde tuttuğun pozisyonlar `AUTO_SELECT` açık olsa da olmasa da her
çalıştırmada satış sinyali için ayrıca kontrol edilir — yani taramanın dışında
kalan bir hisseyi satman gerektiğinde bot bunu kaçırmaz.

## 5. Çalıştırma

```bash
python bot.py
```

Konsolda ve `bot_log.txt` dosyasında her hisse için skor, sinyal ve alınan/alınacak
aksiyonu göreceksin.

## 6. Günlük otomatik çalıştırma

İki seçenek var: bilgisayarında zamanlanmış görev, ya da bilgisayarın kapalıyken bile
çalışan bulut tabanlı çözüm (GitHub Actions).

### Seçenek A — Kendi bilgisayarında (bilgisayar açık olmalı)

Göstergeler günlük veriye dayandığı için botu **günde bir kez**, ABD borsası kapanışına
yakın (16:00 ET) çalıştırmak mantıklıdır. Türkiye saatiyle bu, yaz saati uygulamasına
göre yaklaşık 22:00-23:00'a denk gelir — tam saati çalıştırmadan önce kontrol et.

- **Windows:** Görev Zamanlayıcı (Task Scheduler) → "Temel Görev Oluştur" → günlük tetikleyici →
  eylem olarak `venv\Scripts\python.exe bot.py` komutunu, çalışma dizini olarak proje
  klasörünü seç.
- **Mac:** `crontab -e` ile şuna benzer bir satır ekle (saat TR saatine göre ayarlanır):
  ```
  0 23 * * 1-5 cd /Users/kullanici_adi/alpaca-signal-bot && venv/bin/python bot.py
  ```

### Seçenek B — Bulutta, bilgisayarın kapalıyken de çalışsın (GitHub Actions)

Bu proje `.github/workflows/daily-bot.yml` dosyasıyla birlikte geliyor — GitHub Actions,
her gün (Pzt-Cuma 21:30 UTC, ABD kapanışından sonra) botu kendi sunucularında otomatik
çalıştırır. Tamamen ücretsizdir. Kurulum:

1. **GitHub hesabı aç** (yoksa) — github.com üzerinden ücretsiz kayıt.
2. **Yeni bir repo oluştur** — sağ üstten "New repository", ismini istediğin gibi ver,
   **Private** seç (herkese açık olmasın), "Create repository"ye bas.
3. **Dosyaları yükle** — repo sayfasında "Add file" → "Upload files" ile bu klasördeki
   TÜM dosya ve klasörleri (`.github` klasörü dahil) sürükle-bırak yap.
   **`.env` dosyasını ve `venv` klasörünü YÜKLEME** — API anahtarların içinde, repoya
   girmemeli. (`.gitignore` dosyası zaten bunları hariç tutmak için var, ama Upload Files
   arayüzü .gitignore'u otomatik uygulamayabilir — elle de eklemediğinden emin ol.)
   Alt köşeden "Commit changes"e bas.
4. **API anahtarlarını "Secret" olarak ekle** — repo içinde **Settings → Secrets and
   variables → Actions → New repository secret**:
   - İsim: `ALPACA_API_KEY`, Değer: Alpaca paper API key'in
   - İsim: `ALPACA_SECRET_KEY`, Değer: Alpaca paper secret'ın

   Bu ikisi şifreli saklanır, repo'yu görebilen biri bile bunları okuyamaz.
5. **Test et** — repo içinde **Actions** sekmesine git, "Daily Signal Bot" workflow'unu
   seç, sağdan **"Run workflow"** butonuyla hemen elle tetikle. Birkaç dakika içinde
   tamamlanır; tıklayıp loglarını (ne aldığını/sattığını) orada görebilirsin.
6. Bundan sonra her gün otomatik olarak, bilgisayarın kapalı olsa bile çalışacak.
   Ayarları (hangi hisseler, `AUTO_SELECT`, `ALLOCATION_PER_TRADE_USD` vb.) değiştirmek
   istersen `.github/workflows/daily-bot.yml` dosyasını GitHub üzerinden düzenleyebilirsin
   (kalem ikonuna tıkla, değiştir, "Commit changes").

**Not:** Cron zamanlaması UTC'dir; `30 21 * * 1-5` = Pazartesi-Cuma 21:30 UTC. Bu,
ABD piyasa kapanışından (16:00 ET) hem yaz hem kış saatinde sonraya denk gelecek şekilde
ayarlandı. GitHub'ın ücretsiz zamanlayıcısı bazen birkaç dakika gecikebilir, bu normaldir.


## 7. Gerçek paraya geçiş — dikkat

Bot şu anda **sadece paper (sanal) hesaba** bağlanacak şekilde yazıldı (`paper=True`,
`bot.py` içinde sabit). Paper sonuçlardan tatmin olmadan bu satırı değiştirme.
Gerçek hesaba geçiş, Alpaca'da ayrı bir KYC/onay süreci gerektirir ve bilinçli,
ayrı bir adım olarak ele alınmalıdır.

## Strateji güncellemesi — kurumsal trend-takip prensipleri

Sistem, tanınmış trend-takip yaklaşımlarından (Turtle Traders, Paul Tudor Jones,
Ed Seykota tarzı sistemler) iki önemli prensiple güçlendirildi:

1. **Ana trend filtresi (SMA200):** Fiyat 200 günlük ortalamanın altındaysa —
   yani hisse uzun vadeli düşüş rejimindeyse — AL sinyalleri bastırılır. "Düşen
   bıçağı yakalamaya çalışmak" yerine, sadece ana trendle aynı yönde işlem
   açılır. `TREND_FILTER_ENABLED=false` ile kapatılabilir.
2. **ATR (volatilite) bazlı stop-loss/hedef:** Sabit %3/%6 yerine, her hissenin
   kendi güncel oynaklığına (Average True Range) göre stop mesafesi hesaplanır
   — volatil bir hissede stop çok sıkı, sakin bir hissede çok gevşek olmaz.
   Varsayılan: stop = giriş − 2×ATR, hedef = giriş + 4×ATR (2:1 kazanç/risk
   oranı). `USE_ATR_STOPS=false` ile eski sabit yüzde yöntemine dönülebilir.

**Dürüst bir not:** Bu değişiklikler sistemi daha "kurallı" ve disiplinli hale
getirir, ama **hiçbir teknik gösterge kombinasyonu kâr garantisi vermez.**
Birkaç haftalık/aylık sonuca bakıp strateji hakkında kesin yargıya varmak
istatistiksel olarak güvenilir değildir — kısa vadede en iyi stratejiler bile
kayıpta olabilir. Anlamlı bir değerlendirme için genellikle çok daha uzun bir
gözlem süresi (aylar, onlarca işlem) gerekir.



- Göstergeler gecikmeli (lagging) ve gün içi/anlık al-sat için tasarlanmadı.
- Ücretsiz Alpaca veri planı IEX beslemesini kullanır, SIP (tam piyasa) verisine göre
  küçük farklar olabilir.
- Bot; haber, kazanç açıklaması, makroekonomik olay gibi fiyatı aniden hareket
  ettirebilecek şeyleri bilmez, sadece geçmiş fiyat serisine bakar.
