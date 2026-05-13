# bot/risk.py

import pandas as pd
from config.settings import (
    RANGE_DD_GUARD_PCT, RANGE_MAX_HOLD_BARS,
    TREND_DD_GUARD_PCT, TREND_MAX_HOLD_BARS,
    TREND_TRAIL_ENABLED, TREND_TRAIL_START_POINTS, TREND_TRAIL_DISTANCE_POINTS,
    MNQ_TICK_SIZE, MNQ_TICK_VALUE
)


def adverse_move_pct(side: str, entry_price: float, current_price: float) -> float:
    if side == "LONG":
        return (entry_price - current_price) / entry_price * 100
    if side == "SHORT":
        return (current_price - entry_price) / entry_price * 100
    return 0.0


def unrealized_pnl_pct(side: str, entry_price: float, current_price: float) -> float:
    if side == "LONG":
        return (current_price - entry_price) / entry_price * 100
    if side == "SHORT":
        return (entry_price - current_price) / entry_price * 100
    return 0.0


def range_opposite_exit(row, side: str) -> bool:
    """
    Original ZLC exit:
    LONG exits on MACD cross down while MACD > 0.
    SHORT exits on MACD cross up while MACD < 0.
    """
    if side == "LONG":
        return bool(row["cross_down"] and row["macd"] > 0)
    if side == "SHORT":
        return bool(row["cross_up"] and row["macd"] < 0)
    return False


def trend_ema20_exit(row, side: str) -> bool:
    """
    TREND fallback exit:
    LONG exits if price breaks below EMA20.
    SHORT exits if price breaks above EMA20.
    """
    if pd.isna(row["ema20"]):
        return False
    close = float(row["close"])
    ema20_val = float(row["ema20"])
    if side == "LONG" and close < ema20_val:
        return True
    if side == "SHORT" and close > ema20_val:
        return True
    return False


def trend_trailing_exit(
    side: str,
    entry_price: float,
    current_price: float,
    trade_high: float,
    trade_low: float
) -> bool:
    """
    TREND-only trailing take profit.
    Activates only after TREND_TRAIL_START_POINTS profit has been reached.
    """
    if not TREND_TRAIL_ENABLED:
        return False

    if side == "LONG":
        open_profit_points = trade_high - entry_price
        if open_profit_points >= TREND_TRAIL_START_POINTS:
            trailing_stop = trade_high - TREND_TRAIL_DISTANCE_POINTS
            if current_price <= trailing_stop:
                return True

    if side == "SHORT":
        open_profit_points = entry_price - trade_low
        if open_profit_points >= TREND_TRAIL_START_POINTS:
            trailing_stop = trade_low + TREND_TRAIL_DISTANCE_POINTS
            if current_price >= trailing_stop:
                return True

    return False


def get_risk_params(strategy_mode: str):
    if strategy_mode == "RANGE":
        return RANGE_DD_GUARD_PCT, RANGE_MAX_HOLD_BARS
    if strategy_mode == "TREND":
        return TREND_DD_GUARD_PCT, TREND_MAX_HOLD_BARS
    return RANGE_DD_GUARD_PCT, RANGE_MAX_HOLD_BARS


def calculate_mfe_mae(
    side: str,
    entry_price: float,
    trade_high: float,
    trade_low: float
) -> tuple[float, float]:
    """Returns MFE and MAE in MNQ index points."""
    if side == "LONG":
        return trade_high - entry_price, entry_price - trade_low
    if side == "SHORT":
        return entry_price - trade_low, trade_high - entry_price
    return 0.0, 0.0


def points_to_dollars(points: float, qty: int) -> float:
    ticks = points / MNQ_TICK_SIZE
    return ticks * MNQ_TICK_VALUE * qty
