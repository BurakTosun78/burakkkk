# Binance Vadeli İşlem Botu

Binance USDT-M sürekli vadeli (perpetual) sözleşmelerde EMA kesişimi stratejisiyle
otomatik long/short açan Python botu.

> **Uyarı:** Kaldıraçlı işlemlerde paranızın tamamını kaybedebilirsiniz. Bu bot kâr
> garantisi vermez. Önce backtest, sonra `paper`, sonra `demo` modunda deneyin;
> gerçek paraya en son ve küçük tutarla geçin.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # yalnızca demo/live modları için anahtar gerekir
```

## Kullanım

```bash
python -m bot backtest --days 365   # stratejiyi son 1 yılın verisinde test et
python -m bot run                   # botu çalıştır (config.yaml -> mode)
python -m pytest                    # testler
```

Tüm ayarlar `config.yaml` içindedir (parite, zaman dilimi, strateji, risk).

| mode    | Fiyat verisi | Emirler                   | API anahtarı |
|---------|--------------|---------------------------|--------------|
| `paper` | gerçek       | bot içinde simüle edilir  | gerekmez     |
| `demo`  | demo borsa   | Binance demo hesabına     | [demo.binance.com](https://demo.binance.com) anahtarı |
| `live`  | gerçek       | **gerçek hesaba**         | gerçek anahtar + `--confirm-live` |

Gerçek API anahtarı oluştururken yalnızca **Futures** yetkisi verin, **para çekme
(withdraw) yetkisi vermeyin** ve mümkünse IP kısıtı koyun. Hesap tek yönlü
(one-way) pozisyon modunda olmalıdır.

## Strateji

- **Giriş:** EMA(20), EMA(50)'yi yukarı keserse long, aşağı keserse short. RSI
  aşırı alım/satım bölgesindeyse (70/30) girilmez. Sinyal yalnızca kapanmış mumdan üretilir.
- **Çıkış:** zarar durdur = 2×ATR, kâr al = 3×ATR (borsaya emir olarak konur), ya da ters sinyal.
- **Risk:** stop olunca kasanın en fazla %1'i kaybedilecek şekilde pozisyon
  büyüklüğü hesaplanır; kaldıraç 3x, izole marjin. Gün içinde kasa %5 düşerse o gün yeni işlem açılmaz.

## Yapı

```
bot/config.py      ayarların okunması ve doğrulanması
bot/indicators.py  EMA, RSI, ATR
bot/strategy.py    sinyal üretimi
bot/risk.py        pozisyon büyüklüğü, SL/TP fiyatları
bot/engine.py      simüle hesap (backtest ve paper ortak)
bot/backtest.py    geçmiş veri testi
bot/exchange.py    Binance bağlantısı, mum verisi (ccxt)
bot/live.py        demo/live emir gönderimi
bot/runner.py      canlı döngü
```

## Bilinen sınırlar

- Backtest ve paper modunda fonlama (funding) ücretleri hesaplanmaz.
- Backtest, aynı mumda hem SL hem TP görülürse SL'yi sayar (kötümser varsayım).
- Bot durdurulduğunda açık pozisyon ve SL/TP emirleri borsada kalır.
- Binance bazı ülkelerden API erişimini engeller (HTTP 451).
