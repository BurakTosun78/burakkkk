"""Binance'in herkese açık veri arşivinden (data.binance.vision) geçmiş mum verisi indirir.

API'ye erişilemeyen yerlerde backtest verisi almak için. Yalnızca tamamlanmış aylar bulunur.
"""
import io
import urllib.error
import urllib.request
import zipfile

import pandas as pd

from .exchange import COLUMNS

URL = "https://data.binance.vision/data/futures/um/monthly/klines/{s}/{tf}/{s}-{tf}-{y}-{m:02d}.zip"


def fetch_archive(symbol: str, tf: str, months: int) -> pd.DataFrame:
    """Son `months` tamamlanmış ayın mumları. symbol: 'BTC/USDT:USDT' biçiminde."""
    s = symbol.split(":")[0].replace("/", "")
    end = pd.Timestamp.now(tz="UTC").tz_localize(None).to_period("M") - 1
    frames = []
    for p in pd.period_range(end - months + 1, end, freq="M"):
        try:
            raw = urllib.request.urlopen(URL.format(s=s, tf=tf, y=p.year, m=p.month), timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:  # o ay arşivde yok (parite henüz listelenmemiş ya da ay yayımlanmamış)
                continue
            raise
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=range(6), names=COLUMNS)
        frames.append(df[pd.to_numeric(df["ts"], errors="coerce").notna()])  # başlık satırını at
    if not frames:
        raise SystemExit(f"arşivde {s} {tf} verisi bulunamadı")
    df = pd.concat(frames).astype(float).astype({"ts": "int64"})
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
