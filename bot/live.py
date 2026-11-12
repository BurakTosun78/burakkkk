"""demo / live modu: emirleri Binance'e gönderir. Tek yönlü (one-way) pozisyon modu varsayılır."""
import json
import logging
from pathlib import Path

from .config import Config
from .risk import position_size, stop_prices

log = logging.getLogger("bot")


class LiveBroker:
    def __init__(self, ex, cfg: Config, state_path: Path):
        self.ex, self.cfg, self.state_path = ex, cfg, state_path
        self.symbol = cfg.symbol

    def setup(self) -> None:
        self.ex.load_markets()
        try:
            self.ex.set_margin_mode("isolated", self.symbol)
        except Exception as e:  # zaten isolated ise Binance hata döndürür
            log.info("marjin modu değiştirilmedi: %s", e)
        self.ex.set_leverage(self.cfg.risk.leverage, self.symbol)

    def equity(self) -> float:
        return float(self.ex.fetch_balance()["USDT"]["total"])

    def position(self) -> tuple[int, float]:
        """(yön, miktar); pozisyon yoksa (0, 0.0)."""
        for p in self.ex.fetch_positions([self.symbol]):
            qty = abs(float(p.get("contracts") or 0))
            if qty:
                return (1 if p["side"] == "long" else -1), qty
        return 0, 0.0

    def cancel_orders(self) -> None:
        """Bekleyen normal ve koşullu (SL/TP) emirleri iptal et."""
        for params in ({}, {"trigger": True}):
            try:
                self.ex.cancel_all_orders(self.symbol, params)
            except Exception as e:
                log.warning("emir iptali başarısız %s: %s", params, e)

    def close(self, side: int, qty: float) -> None:
        self.ex.create_order(self.symbol, "market", "sell" if side == 1 else "buy", qty, None, {"reduceOnly": True})

    def halted(self, equity: float) -> bool:
        """Günlük zarar limiti: UTC gün başındaki kasaya göre."""
        day = self.ex.milliseconds() // 86_400_000
        st = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        if st.get("day") != day:
            st = {"day": day, "start_equity": equity}
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(st))
        return equity <= st["start_equity"] * (1 - self.cfg.risk.max_daily_loss)

    def on_signal(self, signal: int, atr: float) -> None:
        side, qty = self.position()
        if side == 0:
            self.cancel_orders()  # SL/TP'den biri dolduysa diğeri artık sahipsiz
        if not signal:
            return
        if side == -signal:
            log.info("ters sinyal: pozisyon kapatılıyor")
            self.cancel_orders()
            self.close(side, qty)
            side = 0
        if side != 0:
            return

        equity = self.equity()
        if self.halted(equity):
            log.warning("günlük zarar limiti aşıldı: yeni işlem yok")
            return
        price = float(self.ex.fetch_ticker(self.symbol)["last"])
        market = self.ex.market(self.symbol)
        qty = float(self.ex.amount_to_precision(self.symbol, position_size(equity, price, atr, self.cfg)))
        min_qty = (market["limits"]["amount"] or {}).get("min") or 0
        min_cost = (market["limits"]["cost"] or {}).get("min") or 0
        if qty <= 0 or qty < min_qty or qty * price < min_cost:
            log.warning("miktar borsa minimumunun altında (%s), işlem açılmadı", qty)
            return

        buy, sell = ("buy", "sell") if signal == 1 else ("sell", "buy")
        order = self.ex.create_order(self.symbol, "market", buy, qty)
        entry = float(order.get("average") or price)
        sl, tp = stop_prices(signal, entry, atr, self.cfg)
        log.info("%s %s @ %.2f  SL %.2f  TP %.2f", "LONG" if signal == 1 else "SHORT", qty, entry, sl, tp)
        try:
            p = self.ex.price_to_precision
            self.ex.create_order(self.symbol, "market", sell, qty, None,
                                 {"stopLossPrice": p(self.symbol, sl), "reduceOnly": True})
            self.ex.create_order(self.symbol, "market", sell, qty, None,
                                 {"takeProfitPrice": p(self.symbol, tp), "reduceOnly": True})
        except Exception:
            # Stopsuz pozisyon taşımaktansa hemen kapat.
            log.exception("SL/TP emri verilemedi: pozisyon kapatılıyor")
            self.cancel_orders()
            self.close(signal, qty)
            raise
