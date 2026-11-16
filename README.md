# Binance Vadeli İşlem Botu

Binance USDT-M sürekli vadeli (perpetual) sözleşmelerde EMA kesişimi (trend takibi) stratejisiyle
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
python -m bot backtest --days 365   # stratejiyi son 1 yılın verisinde test et (API)
python -m bot backtest --archive 36 # API yerine açık veri arşivinden son 36 ay
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

- **Giriş:** 4 saatlik mumlarda EMA(20), EMA(50)'yi yukarı keserse long, aşağı keserse short. RSI
  aşırı alım/satım bölgesindeyse (70/30) girilmez. Sinyal yalnızca kapanmış mumdan üretilir.
- **Çıkış:** zarar durdur = 3×ATR (borsaya emir olarak konur) ya da ters sinyal. Sabit kâr al
  yoktur (`tp_atr: 0`); trend sürdükçe pozisyon taşınır.
- **Risk:** stop olunca kasanın en fazla %1'i kaybedilecek şekilde pozisyon
  büyüklüğü hesaplanır; kaldıraç 3x, izole marjin. Gün içinde kasa %5 düşerse o gün yeni işlem açılmaz.

## Gerçek veride sonuçlar

Binance açık veri arşivi, Kasım 2023 – Ekim 2026 (3 yıl), komisyon %0,05 + kayma %0,02 dahil,
fonlama ücretleri hariç. Tekrar üretmek için: `python -m bot backtest --archive 36`

| Parite | İşlem | Toplam getiri | Yıllık | Günlük ort. | Maks. düşüş |
|--------|-------|---------------|--------|-------------|-------------|
| BTC    | 100   | +%11,6        | %3,7   | %0,010      | −%16,1      |
| ETH    | 110   | +%14,7        | %4,7   | %0,013      | −%21,7      |
| SOL    | 117   | +%13,4        | %4,3   | %0,012      | −%17,2      |

Bunlar geçmiş sonuçlardır, gelecek için garanti değildir. Ayarlar aynı veriye bakılarak
seçildiği için gerçek performans büyük olasılıkla daha düşük olur.

Denenip **elenen** ayarlar (aynı veri):

- İlk sürüm (1 saatlik, SL 2×ATR, TP 3×ATR): BTC −%45, ETH −%35, SOL −%12.
- 15 dakikalık: üç paritede de kasa %94–99 eridi (komisyonlar kârı yiyor).
- Riski/kaldıracı artırmak (işlem başı %5, 20x): BTC −%90.

**Günde %2–3 hedefi hakkında:** Günlük %2 bileşik getiri yılda yaklaşık 1.377 kat, %3 ise
yaklaşık 48.000 kat demektir. Bunu düşük riskle sağlayan bilinen bir strateji yoktur; bu bot
da sağlamaz.

## Yapı

```
bot/config.py      ayarların okunması ve doğrulanması
bot/indicators.py  EMA, RSI, ATR
bot/strategy.py    sinyal üretimi
bot/risk.py        pozisyon büyüklüğü, SL/TP fiyatları
bot/engine.py      simüle hesap (backtest ve paper ortak)
bot/backtest.py    geçmiş veri testi
bot/exchange.py    Binance bağlantısı, mum verisi (ccxt)
bot/vision.py      açık veri arşivinden geçmiş mum indirme
bot/live.py        demo/live emir gönderimi
bot/runner.py      canlı döngü
```

## Bilinen sınırlar

- Backtest ve paper modunda fonlama (funding) ücretleri hesaplanmaz.
- Backtest, aynı mumda hem SL hem TP görülürse SL'yi sayar (kötümser varsayım).
- Bot durdurulduğunda açık pozisyon ve SL/TP emirleri borsada kalır.
- Binance bazı ülkelerden API erişimini engeller (HTTP 451).
