"""
Trading calculations — lot sizing, pip values, PnL.

All calculations are based on symbol specifications from symbols.yaml.
"""

import math
from loguru import logger


def calculate_lot_size(
    balance: float,
    risk_pct: float,
    sl_distance_pips: float,
    pip_value_per_lot: float,
    min_volume: float = 0.01,
    volume_step: float = 0.01,
    max_lot: float = 1.0,
) -> float:
    """
    Calculate position size based on risk percentage.

    Formula: lot = (balance × risk%) / (SL_pips × pip_value_per_lot)

    Args:
        balance: Account balance in USD
        risk_pct: Risk per trade as decimal (0.01 = 1%)
        sl_distance_pips: Stop loss distance in pips
        pip_value_per_lot: Dollar value per pip per 1.0 lot
        min_volume: Minimum lot size allowed
        volume_step: Lot size increment
        max_lot: Maximum lot size (hard cap)

    Returns:
        Calculated lot size, rounded to volume_step

    Examples:
        XAUUSD ($10K, 1% risk, 50 pip SL):
        lot = (10000 × 0.01) / (50 × 1.0) = 2.0 lots

        EURUSD ($10K, 1% risk, 30 pip SL):
        lot = (10000 × 0.01) / (30 × 10.0) = 0.033 → 0.03 lots
    """
    if sl_distance_pips <= 0:
        logger.error("SL distance must be positive, got {}", sl_distance_pips)
        return min_volume

    risk_amount = balance * risk_pct
    raw_lot = risk_amount / (sl_distance_pips * pip_value_per_lot)

    # Round down to volume step
    lot = math.floor(raw_lot / volume_step) * volume_step

    # Clamp to min/max
    lot = max(min_volume, min(lot, max_lot))

    logger.debug(
        "Lot calc: balance={}, risk={}%, SL={} pips, pip_val={} → raw={:.4f} → lot={:.2f}",
        balance, risk_pct * 100, sl_distance_pips, pip_value_per_lot, raw_lot, lot,
    )
    return lot


def calculate_sl_distance_pips(
    entry_price: float,
    sl_price: float,
    pip_size: float,
) -> float:
    """
    Calculate SL distance in pips.

    Args:
        entry_price: Entry price
        sl_price: Stop loss price
        pip_size: Size of 1 pip for the symbol (0.0001 for forex, 0.10 for gold)

    Returns:
        Distance in pips (always positive)
    """
    return abs(entry_price - sl_price) / pip_size


def calculate_tp_price(
    entry_price: float,
    sl_price: float,
    rr_ratio: float,
    direction: str,
) -> float:
    """
    Calculate TP price from entry, SL, and RR ratio.

    Args:
        entry_price: Entry price
        sl_price: Stop loss price
        rr_ratio: Risk-reward ratio (e.g., 1.5, 2.0, 3.0)
        direction: "BUY" or "SELL"

    Returns:
        Take profit price
    """
    sl_distance = abs(entry_price - sl_price)
    tp_distance = sl_distance * rr_ratio

    if direction == "BUY":
        return entry_price + tp_distance
    else:
        return entry_price - tp_distance


def calculate_pnl(
    direction: str,
    open_price: float,
    close_price: float,
    lot_size: float,
    contract_size: float,
) -> float:
    """
    Calculate profit/loss for a trade.

    Args:
        direction: "BUY" or "SELL"
        open_price: Entry price
        close_price: Current/close price
        lot_size: Trade volume
        contract_size: Contract size (100 for gold, 100000 for forex)

    Returns:
        PnL in account currency (USD)
    """
    if direction == "BUY":
        pnl = (close_price - open_price) * lot_size * contract_size
    else:
        pnl = (open_price - close_price) * lot_size * contract_size
    return round(pnl, 2)


def calculate_risk_amount(balance: float, risk_pct: float) -> float:
    """Calculate dollar risk amount."""
    return round(balance * risk_pct, 2)


def pips_to_price(pips: float, pip_size: float) -> float:
    """Convert pips to price distance."""
    return pips * pip_size


def price_to_pips(price_distance: float, pip_size: float) -> float:
    """Convert price distance to pips."""
    if pip_size == 0:
        return 0.0
    return price_distance / pip_size
