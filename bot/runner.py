"""Canlı döngü: her mum kapanışında sinyale bakar."""
import json
import logging
import time
from pathlib import Path

from .config import Config
from .engine import SimAccount
from .exchange import closed_candles, make_exchange, timeframe_ms
from .live import LiveBroker
from .strategy import add_signals

log = logging.getLogger("bot")
STATE = Path("state")


def _load_paper(cfg: Config, path: Path) -> tuple[SimAccount, int]:
    if path.exists():
        d = json.loads(path.read_text())
        return SimAccount.from_dict(cfg, d["account"]), d["last_ts"]
    return SimAccount(cfg, cfg.paper.initial_balance), 0


def step_paper(acc: SimAccount, last_ts: int, df, cfg: Config) -> int:
    """Yeni kapanmış mum varsa işle; işlenen son mumun zamanını döndür."""
    bar = add_signals(df, cfg.strategy).iloc[-1]
    if bar.ts <= last_ts:
        return last_ts
    # Kapanış fiyatı ~ sonraki mumun açılışı: backtest ile aynı varsayım.
    for e in acc.on_bar(int(bar.ts), bar.open, bar.high, bar.low, int(bar.signal), bar.atr, bar.close):
        log.info("[paper] %s", e)
    log.info("[paper] kapanış %.2f  kasa %.2f USDT  pozisyon %s", bar.close, acc.equity(bar.close),
             {1: "LONG", -1: "SHORT"}[acc.position.side] if acc.position else "yok")
    return int(bar.ts)


def run(cfg: Config) -> None:
    ex = make_exchange(cfg.mode)
    tf = timeframe_ms(cfg.timeframe)
    name = cfg.symbol.replace("/", "").replace(":", "_")
    log.info("mod=%s  %s  %s", cfg.mode, cfg.symbol, cfg.timeframe)

    if cfg.mode == "paper":
        path = STATE / f"paper_{name}.json"
        acc, last_ts = _load_paper(cfg, path)
    else:
        broker = LiveBroker(ex, cfg, STATE / f"{cfg.mode}_{name}.json")
        broker.setup()
        last_ts = 0

    while True:
        try:
            df = closed_candles(ex, cfg.symbol, cfg.timeframe)
            if len(df) < cfg.strategy.ema_slow + 2:
                raise RuntimeError("yeterli mum verisi yok")
            if cfg.mode == "paper":
                new_ts = step_paper(acc, last_ts, df, cfg)
                if new_ts != last_ts:
                    last_ts = new_ts
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"account": acc.to_dict(), "last_ts": last_ts}))
            else:
                bar = add_signals(df, cfg.strategy).iloc[-1]
                if bar.ts > last_ts:
                    # İlk turda eski mumun sinyaliyle işlem açma; yalnızca emirleri/pozisyonu denetle.
                    signal = int(bar.signal) if last_ts else 0
                    broker.on_signal(signal, bar.atr)
                    last_ts = int(bar.ts)
                    log.info("[%s] kapanış %.2f  sinyal %d  pozisyon %s", cfg.mode, bar.close, signal, broker.position())
        except KeyboardInterrupt:
            raise
        except Exception:
            log.exception("döngü hatası, 30 sn sonra tekrar denenecek")
            time.sleep(30)
            continue
        # Sonraki mum kapanışından 3 sn sonrasına kadar bekle.
        now = ex.milliseconds()
        time.sleep(max(1, ((now // tf + 1) * tf - now) / 1000 + 3))
