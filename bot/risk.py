from .config import Config


def position_size(equity: float, price: float, atr: float, cfg: Config) -> float:
    """Stop olunca kasanın risk_per_trade kadarı kaybedilecek şekilde miktar (coin adedi).

    0 dönerse işlem açılmaz.
    """
    if not (equity > 0 and price > 0 and atr > 0):  # NaN'ları da eler
        return 0.0
    stop_dist = cfg.strategy.sl_atr * atr
    # Stop, likidasyon seviyesine (kabaca fiyat/kaldıraç) yakınsa işlem açma.
    if stop_dist / price >= 0.8 / cfg.risk.leverage:
        return 0.0
    qty = equity * cfg.risk.risk_per_trade / stop_dist
    max_qty = equity * cfg.risk.leverage / price
    return min(qty, max_qty)


def stop_prices(side: int, entry: float, atr: float, cfg: Config) -> tuple[float, float]:
    """(zarar durdur, kâr al) fiyatları."""
    return entry - side * cfg.strategy.sl_atr * atr, entry + side * cfg.strategy.tp_atr * atr
