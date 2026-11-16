# Borsa Bot: ABD Hisseleri Gün İçi Yapay Zekâ Al-Sat

LightGBM modeli (Microsoft Qlib'in Alpha158 özelliklerinden esinlenildi) + Alpaca API.
Her 5 dakikada 10 likit hisse/ETF'yi tarar. Sonraki 30 dakikada yükselme olasılığı yüksek olanları
**stop-loss ve kâr-al emirleriyle birlikte** alır. Gün sonunda bütün pozisyonları kapatır, geceye pozisyon taşımaz.

> ⚠️ Bu yazılım yatırım tavsiyesi değildir ve kâr garantisi vermez. Gün içi işlem yapan bireysel yatırımcıların
> çoğu para kaybeder. Kaybetmeyi göze alamayacağın parayla çalıştırma.

## Dosyalar
| Dosya | Ne yapar |
|---|---|
| `config.py` | Tüm ayarlar: semboller, eşikler, **risk limitleri** |
| `data.py` | Alpaca'dan 5 dakikalık mum verisi |
| `features.py` | 22 teknik özellik (momentum, volatilite, VWAP, RSI, piyasaya göre güç…) |
| `model.py` | LightGBM + walk-forward eğitim |
| `risk.py` | Pozisyon boyutu + devre kesiciler |
| `backtest.py` | Kayma payı dahil gerçekçi geçmiş test |
| `run_backtest.py` | **İlk çalıştırılacak dosya** |
| `live_trader.py` | Canlı bot (varsayılan: sanal hesap) |
| `telegram_rapor.py` | Gün sonu kâr/zarar raporu + kritik uyarılar |
| `.github/workflows/` | Bulutta otomatik çalıştırma (trader, gün sonu raporu, backtest) |
| `eski_gunluk_bot/` | Önceki günlük SMA/RSI/MACD botu (arşiv, artık çalışmıyor) |

## Kurulum (Windows)
1. Python 3.11 veya üstünü kur ("Add to PATH" işaretli olsun).
2. Klasörde terminal aç: `pip install -r requirements.txt`
3. https://alpaca.markets adresinde ücretsiz hesap aç. Paper Trading bölümünden API Key ve Secret al.
   (Gerçek hesap Türkiye'den açılabiliyor mu, Alpaca'nın uluslararası hesap sayfasından kontrol et. Açılamıyorsa
   aynı mantık Interactive Brokers'a uyarlanabilir.)
4. `.env.example` dosyasını `.env` olarak kopyala ve anahtarları yaz.

## Kullanım: 3 aşama, sırayla
**1. Backtest:** `python run_backtest.py`
Model son 120 günün hiç görmediği kısımlarında test edilir. Şu üçü sağlanmadan 2. aşamaya geçme:
- Ortalama AUC **≥ 0.52**
- Sharpe **≥ 1.0**
- Toplam getiri **SPY al-tut'tan yüksek**

**2. Sanal hesap (en az 4 hafta):** `python live_trader.py`
Gerçek piyasada sanal parayla işlem yapar. `bot_log.txt` ve `islemler.csv` dosyalarını takip et.
Backtest ile sanal hesap sonuçları birbirine yakın değilse bir sorun var demektir; gerçek paraya geçme.

**3. Gerçek para (karar senin):** `.env` içinde `PAPER=false` yap ve
`python live_trader.py --live-onay` ile çalıştır. Çift kilit var, yanlışlıkla gerçek parayla başlamaz.
Küçük bir tutarla başla.


## Bulutta çalıştırma (GitHub Actions): bilgisayar kapalıyken de çalışır
Repo'daki **Settings → Secrets and variables → Actions** bölümünde şu 4 secret olmalı:
`ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (zaten var), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (yeni).

| Workflow | Ne zaman | Ne yapar |
|---|---|---|
| Gun Ici AI Trader | Hafta içi her gün, seans boyunca (2 parça) | 5 dakikada bir tarar, al-sat yapar |
| Gun Sonu Telegram Raporu | Hafta içi TR saatiyle 00:20 | Günlük K/Z, işlemler, açık pozisyonlar |
| Backtest (elle calistir) | Sen tetikleyince | Model testini yapar, sonucu Telegram'a atar |

## Telegram kurulumu (5 dakika)
1. Telegram'da **@BotFather**'a yaz → `/newbot` → bir isim ver → verilen **token**'ı kopyala.
2. Oluşan botuna Telegram'dan herhangi bir mesaj at (örneğin "merhaba").
3. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini aç. `"chat":{"id":123456789` kısmındaki sayı senin **chat id**'n.
4. İkisini GitHub Secrets'a ekle. Actions → "Gun Sonu Telegram Raporu" → **Run workflow** ile hemen dene.

Bot ayrıca şu durumlarda anında mesaj atar: günlük zarar limiti doldu, maksimum düşüşte bot durdu, art arda hata.

## Risk kuralları (`config.py`)
- İşlem başına en fazla sermayenin **%0.5'i** riske girer (stop olursa kayıp bu kadar)
- Tek hissede en fazla %15, aynı anda en fazla 4 pozisyon
- Gün içinde **%2** kayıpta bot o gün yeni işlem açmaz
- Zirveden **%10** düşüşte bot her şeyi kapatıp kendini durdurur
- Kapanışa 10 dakika kala bütün pozisyonlar kapatılır

## Geliştirme fikirleri
- Daha fazla sembol ekle (`symbols`), eşikleri backtest ile ayarla. Aşırı ayar yapmak (overfit) en büyük tuzaktır.
- Haber/duygu verisi eklemek (FinGPT), Qlib'in diğer modelleri (LSTM, Transformer, TRA)
- Botu kesintisiz çalıştırmak için bir VPS (aylık birkaç dolar) veya bilgisayarın açık kalması gerekir.

ABD'deki $25.000 "pattern day trader" kuralı 4 Haziran 2026'da kaldırıldı. Aracı kurumlar yeni kurala
2027'ye kadar kademeli geçiyor; kendi hesabındaki durumu kontrol et.
