# bot/strategy.py

import pandas as pd
import numpy as np
from config.settings import (
    FAST_EMA, SLOW_EMA, SIGNAL_EMA,
    EMA_TREND_FAST, EMA_TREND_SLOW,
    ADX_PERIOD, ADX_RANGE_MAX, ADX_TREND_MIN,
    RANGE_MACD_MIN_ABS
)


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    ADX using Wilder's smoothing (alpha = 1/period).
    FIX: original used simple rolling mean which produced wrong ADX values
    and caused incorrect regime classification.
    """
    df = df.copy()

    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm_raw = high.diff()
    minus_dm_raw = -low.diff()

    plus_dm = np.where(
        (plus_dm_raw > minus_dm_raw) & (plus_dm_raw > 0),
        plus_dm_raw, 0.0
    )
    minus_dm = np.where(
        (minus_dm_raw > plus_dm_raw) & (minus_dm_raw > 0),
        minus_dm_raw, 0.0
    )

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing: alpha = 1/period
    alpha = 1 / period
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.ewm(alpha=alpha, adjust=False).mean()

    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ema_fast"] = ema(df["close"], FAST_EMA)
    df["ema_slow"] = ema(df["close"], SLOW_EMA)

    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["macd_signal"] = ema(df["macd"], SIGNAL_EMA)
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["cross_up"] = (
        (df["macd"].shift(1) <= df["macd_signal"].shift(1)) &
        (df["macd"] > df["macd_signal"])
    )
    df["cross_down"] = (
        (df["macd"].shift(1) >= df["macd_signal"].shift(1)) &
        (df["macd"] < df["macd_signal"])
    )

    df["ema20"] = ema(df["close"], EMA_TREND_FAST)
    df["ema50"] = ema(df["close"], EMA_TREND_SLOW)

    df = add_adx(df, ADX_PERIOD)

    return df


def detect_regime(adx: float) -> str:
    if pd.isna(adx):
        return "NONE"
    if adx < ADX_RANGE_MAX:
        return "RANGE"
    if adx > ADX_TREND_MIN:
        return "TREND"
    return "NONE"


def range_zlc_signal(row) -> str | None:
    """
    RANGE MODE — Contrarian MACD-ZLC:
    LONG:  MACD crosses above signal while MACD < 0
    SHORT: MACD crosses below signal while MACD > 0
    """
    if pd.isna(row["macd"]) or pd.isna(row["macd_signal"]):
        return None
    if abs(row["macd"]) < RANGE_MACD_MIN_ABS:
        return None
    if row["cross_up"] and row["macd"] < 0:
        return "LONG"
    if row["cross_down"] and row["macd"] > 0:
        return "SHORT"
    return None


def trend_pullback_signal(row) -> str | None:
    """
    TREND MODE — EMA20/EMA50 pullback continuation:
    LONG:  EMA20 > EMA50, price near EMA20, MACD confirms
    SHORT: EMA20 < EMA50, price near EMA20, MACD confirms
    """
    if pd.isna(row["ema20"]) or pd.isna(row["ema50"]):
        return None
    if pd.isna(row["macd"]) or pd.isna(row["macd_signal"]):
        return None

    close = float(row["close"])
    ema20_val = float(row["ema20"])
    ema50_val = float(row["ema50"])

    near_ema20_long = close <= ema20_val * 1.001
    near_ema20_short = close >= ema20_val * 0.999

    if ema20_val > ema50_val:
        if near_ema20_long and row["macd"] > row["macd_signal"]:
            return "LONG"

    if ema20_val < ema50_val:
        if near_ema20_short and row["macd"] < row["macd_signal"]:
            return "SHORT"

    return None


def get_signal(row) -> tuple[str, str | None]:
    regime = detect_regime(row["adx"])
    if regime == "RANGE":
        return regime, range_zlc_signal(row)
    if regime == "TREND":
        return regime, trend_pullback_signal(row)
    return regime, None
