import argparse
import logging
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from .backtest import run_backtest
from .config import load_config
from .exchange import fetch_history, make_exchange
from .runner import run
from .vision import fetch_archive


def main() -> None:
    ap = argparse.ArgumentParser(prog="bot", description="Binance USDT-M vadeli işlem botu")
    ap.add_argument("-c", "--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bt = sub.add_parser("backtest", help="stratejiyi geçmiş veride test et")
    bt.add_argument("--days", type=int, default=365)
    bt.add_argument("--archive", type=int, metavar="AY",
                    help="API yerine Binance açık veri arşivinden son AY tamamlanmış ayı indir")
    bt.add_argument("--csv", help="Binance yerine bu CSV'den oku (ts,open,high,low,close,volume)")
    rn = sub.add_parser("run", help="botu çalıştır (config.yaml içindeki mode'a göre)")
    rn.add_argument("--confirm-live", action="store_true", help="gerçek parayla işlem yapmayı onayla")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    cfg = load_config(args.config)

    if args.cmd == "backtest":
        if args.csv:
            df = pd.read_csv(args.csv)
        else:
            if args.archive:
                df = fetch_archive(cfg.symbol, cfg.timeframe, args.archive)
            else:
                df = fetch_history(make_exchange(), cfg.symbol, cfg.timeframe, args.days)
            Path("data").mkdir(exist_ok=True)
            df.to_csv(f"data/{cfg.symbol.replace('/', '').replace(':', '_')}_{cfg.timeframe}.csv", index=False)
        res = run_backtest(df, cfg)
        print(f"\n{cfg.symbol} {cfg.timeframe}  {len(df)} mum  "
              f"({pd.to_datetime(df.ts.iloc[0], unit='ms'):%Y-%m-%d} → {pd.to_datetime(df.ts.iloc[-1], unit='ms'):%Y-%m-%d})")
        for k, v in res.stats().items():
            print(f"  {k:<22} {v}")
        print("  (fonlama ücretleri dahil değildir)")
    else:
        if cfg.mode == "live" and not args.confirm_live:
            raise SystemExit("mode: live GERÇEK PARA kullanır. Eminseniz --confirm-live ile çalıştırın.")
        try:
            run(cfg)
        except KeyboardInterrupt:
            print("durduruldu (açık pozisyon ve emirler borsada kalır)")


if __name__ == "__main__":
    main()
