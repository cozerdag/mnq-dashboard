# bot/main.py
#
# MNQ regime-switching bot — all fixes applied:
#   FIX 1:  df.iloc[-2] for completed bar signals
#   FIX 2:  ib.sleep() everywhere instead of time.sleep()
#   FIX 3:  Actual fill price captured from trade.orderStatus.avgFillPrice
#   FIX 4:  ADX uses Wilder's smoothing (in strategy.py)
#   FIX 5:  bot_state.json persistence — survives crashes
#   FIX 6:  last_signal_bar_time — prevents duplicate entries on same bar
#   FIX 7:  bars_held tracked as counter, not bar timestamp diff
#   FIX 8:  IBKR-side protective stop order placed on entry
#   FIX 9:  Net P&L logged after commission
#   FIX 10: Session filter — entries only during quality hours
#   FIX 11: Auto-reconnect on connection loss or market data errors

import csv
import json
import os
from datetime import datetime

import pytz

from bot.connection import (
    connect_ib, reconnect_ib, get_contract,
    fetch_bars, get_position_side_and_qty
)
from bot.strategy import add_indicators, get_signal
from bot.risk import (
    adverse_move_pct, unrealized_pnl_pct,
    range_opposite_exit, trend_ema20_exit, trend_trailing_exit,
    get_risk_params, calculate_mfe_mae, points_to_dollars
)
from bot.order_manager import (
    enter_position, close_position,
    place_stop_order, cancel_order, get_fill_price
)
from config.settings import (
    QTY, POLL_SECONDS,
    TRADE_LOG_FILE, STATE_FILE,
    COMMISSION_PER_SIDE
)


# =========================
# SESSION FILTER
# FIX 10: Only open NEW trades during quality hours.
#
# Session 1 — NY Open:
#   Monitor from 09:30 ET — watch but hold entries (open is chaotic)
#   Entries open at 09:45 ET after the open range settles
#   Entries close at 11:30 ET
#
# Session 2 — NY Afternoon:
#   Entries open  13:00 ET
#   Entries close 15:45 ET (15 min buffer before 16:00 close)
#
# Turkey time (UTC+3):
#   Session 1: 16:45 – 18:30
#   Session 2: 20:00 – 22:45
#
# IMPORTANT: Position management (exits, stop checks) runs 24/7.
# The session filter ONLY blocks new entries.
# =========================

ET = pytz.timezone("America/New_York")

SESSION1_MONITOR_H, SESSION1_MONITOR_M = 9,  30
SESSION1_ENTRY_H,   SESSION1_ENTRY_M   = 9,  45
SESSION1_END_H,     SESSION1_END_M     = 11, 30

SESSION2_START_H,   SESSION2_START_M   = 13, 0
SESSION2_END_H,     SESSION2_END_M     = 15, 45

# Keywords that indicate a connectivity issue worth reconnecting for
RECONNECT_KEYWORDS = [
    "connection", "market data", "socket", "disconnected",
    "timeout", "eoferror", "connectionreset", "no data"
]


def get_session_status() -> str:
    """
    Returns:
        'OPEN'    — entries allowed
        'MONITOR' — NY open buffer 09:30–09:45, watching but not entering
        'CLOSED'  — outside all sessions
        'WEEKEND' — Saturday or Sunday
    """
    now_et = datetime.now(ET)

    if now_et.weekday() >= 5:
        return "WEEKEND"

    t = now_et.hour * 60 + now_et.minute

    s1_monitor = SESSION1_MONITOR_H * 60 + SESSION1_MONITOR_M  # 570
    s1_entry   = SESSION1_ENTRY_H   * 60 + SESSION1_ENTRY_M    # 585
    s1_end     = SESSION1_END_H     * 60 + SESSION1_END_M      # 690
    s2_start   = SESSION2_START_H   * 60 + SESSION2_START_M    # 780
    s2_end     = SESSION2_END_H     * 60 + SESSION2_END_M      # 945

    if s1_monitor <= t < s1_entry:
        return "MONITOR"
    if s1_entry <= t < s1_end:
        return "OPEN"
    if s2_start <= t < s2_end:
        return "OPEN"
    return "CLOSED"


def session_label() -> str:
    status = get_session_status()
    now_et = datetime.now(ET)
    et_str = now_et.strftime("%H:%M ET")
    labels = {
        "OPEN":    f"Session=OPEN ({et_str})",
        "MONITOR": f"Session=MONITOR — holding until 09:45 ET ({et_str})",
        "CLOSED":  f"Session=CLOSED ({et_str})",
        "WEEKEND": f"Session=WEEKEND ({et_str})"
    }
    return labels.get(status, et_str)


def is_connection_error(e: Exception) -> bool:
    """Returns True if the exception looks like a connectivity issue."""
    msg = str(e).lower()
    return any(kw in msg for kw in RECONNECT_KEYWORDS)


# =========================
# STATE PERSISTENCE
# FIX 5: Survives bot crashes
# =========================

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, default=str)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


# =========================
# TRADE LOGGING
# =========================

def ensure_trade_log_exists():
    os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
    if os.path.exists(TRADE_LOG_FILE):
        return
    with open(TRADE_LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "exit_time", "strategy_mode", "side", "qty",
            "entry_time", "exit_reason",
            "entry_price", "exit_price",
            "realized_points", "realized_usd_gross", "realized_usd_net",
            "mfe_points", "mae_points", "mfe_usd", "mae_usd",
            "bars_held"
        ])


def log_trade(
    strategy_mode: str,
    side: str,
    qty: int,
    entry_time,
    exit_reason: str,
    entry_price: float,
    exit_price: float,
    trade_high: float,
    trade_low: float,
    bars_held: int
):
    mfe, mae = calculate_mfe_mae(side, entry_price, trade_high, trade_low)
    realized_points    = (exit_price - entry_price) if side == "LONG" else (entry_price - exit_price)
    realized_usd_gross = points_to_dollars(realized_points, qty)
    realized_usd_net   = realized_usd_gross - (COMMISSION_PER_SIDE * 2)
    mfe_usd = points_to_dollars(mfe, qty)
    mae_usd = points_to_dollars(mae, qty)

    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            strategy_mode, side, qty, entry_time, exit_reason,
            round(entry_price, 2), round(exit_price, 2),
            round(realized_points, 2), round(realized_usd_gross, 2), round(realized_usd_net, 2),
            round(mfe, 2), round(mae, 2),
            round(mfe_usd, 2), round(mae_usd, 2),
            bars_held
        ])


# =========================
# MAIN LOOP
# =========================

def main():
    ensure_trade_log_exists()

    ib = connect_ib()
    contract = get_contract(ib)

    print("[START] Connected to IBKR")
    print(f"[CONTRACT] MNQ {contract.lastTradeDateOrContractMonth}")
    print("[WARNING] Paper trade first.")
    print("[SESSIONS] NY Open entries: 09:45–11:30 ET | Afternoon entries: 13:00–15:45 ET")
    print("[INFO] Turkey time: Session 1 = 16:45–18:30 | Session 2 = 20:00–22:45")

    saved = load_state()
    internal_side          = saved.get("internal_side")
    internal_strategy_mode = saved.get("internal_strategy_mode")
    internal_entry_price   = saved.get("internal_entry_price")
    internal_entry_time    = saved.get("internal_entry_time")
    trade_high             = saved.get("trade_high")
    trade_low              = saved.get("trade_low")
    bars_held              = saved.get("bars_held", 0)

    if saved:
        print(f"[RESUME] Restored state: side={internal_side} entry={internal_entry_price} bars={bars_held}")

    last_signal_bar_time = None
    open_stop_trade      = None
    last_bar_time        = None

    while True:
        try:
            df = fetch_bars(ib, contract)
            df = add_indicators(df)

            signal_row       = df.iloc[-2]          # FIX 1: last completed bar
            current_price    = float(df.iloc[-1]["close"])
            current_bar_time = df.iloc[-1]["timestamp"]

            broker_side, broker_qty = get_position_side_and_qty(ib, contract)
            regime, signal = get_signal(signal_row)
            session = get_session_status()

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Price={current_price:.2f} "
                f"ADX={signal_row['adx']:.2f} "
                f"Regime={regime} "
                f"Signal={signal} "
                f"Pos={broker_side}/{broker_qty} "
                f"Bars={bars_held} "
                f"{session_label()}"
            )

            # FIX 7: increment bars_held on new bar only
            if last_bar_time is not None and current_bar_time != last_bar_time:
                if broker_side is not None:
                    bars_held += 1
            last_bar_time = current_bar_time

            # Reset if broker is flat
            if broker_side is None:
                if internal_side is not None:
                    print("[SYNC] Broker is flat — clearing internal state.")
                internal_side          = None
                internal_strategy_mode = None
                internal_entry_price   = None
                internal_entry_time    = None
                trade_high             = None
                trade_low              = None
                bars_held              = 0
                open_stop_trade        = None
                clear_state()

            # Adopt state if broker has position but state was lost
            if broker_side is not None and internal_side is None:
                internal_side          = broker_side
                internal_strategy_mode = "UNKNOWN"
                internal_entry_price   = current_price
                internal_entry_time    = str(current_bar_time)
                trade_high             = current_price
                trade_low              = current_price
                bars_held              = 0
                print("[SYNC] Existing broker position adopted.")
                print("[SYNC] WARNING: entry_price set to current price — P&L inaccurate for this trade.")

            # =========================
            # POSITION MANAGEMENT
            # Runs 24/7 regardless of session
            # =========================

            if broker_side is not None and broker_qty > 0:
                side          = broker_side
                strategy_mode = internal_strategy_mode or "UNKNOWN"
                entry_price   = internal_entry_price or current_price

                trade_high = max(trade_high or current_price, current_price)
                trade_low  = min(trade_low  or current_price, current_price)

                dd_guard_pct, max_hold_bars = get_risk_params(strategy_mode)
                adverse = adverse_move_pct(side, entry_price, current_price)
                pnl_pct = unrealized_pnl_pct(side, entry_price, current_price)

                exit_reason = None

                if adverse >= dd_guard_pct:
                    exit_reason = "dd_guard"

                elif bars_held >= max_hold_bars and pnl_pct <= 0:
                    exit_reason = "time_stop"

                elif strategy_mode == "RANGE" and range_opposite_exit(signal_row, side):
                    exit_reason = "range_macd_exit"

                elif strategy_mode == "TREND" and trend_trailing_exit(
                    side=side,
                    entry_price=entry_price,
                    current_price=current_price,
                    trade_high=trade_high,
                    trade_low=trade_low
                ):
                    exit_reason = "trend_trailing_tp"

                elif strategy_mode == "TREND" and trend_ema20_exit(signal_row, side):
                    exit_reason = "trend_ema20_exit"

                if exit_reason is not None:
                    print(
                        f"[EXIT] {exit_reason} | {side} qty={broker_qty} "
                        f"entry={entry_price:.2f} exit≈{current_price:.2f} bars={bars_held}"
                    )

                    cancel_order(ib, open_stop_trade)
                    open_stop_trade = None

                    exit_trade        = close_position(ib, contract, side, broker_qty)
                    actual_exit_price = get_fill_price(exit_trade, current_price)

                    log_trade(
                        strategy_mode=strategy_mode,
                        side=side,
                        qty=broker_qty,
                        entry_time=internal_entry_time,
                        exit_reason=exit_reason,
                        entry_price=entry_price,
                        exit_price=actual_exit_price,
                        trade_high=trade_high,
                        trade_low=trade_low,
                        bars_held=bars_held
                    )

                    internal_side          = None
                    internal_strategy_mode = None
                    internal_entry_price   = None
                    internal_entry_time    = None
                    trade_high             = None
                    trade_low              = None
                    bars_held              = 0
                    clear_state()

                    ib.sleep(POLL_SECONDS)
                    continue

                save_state({
                    "internal_side":          internal_side,
                    "internal_strategy_mode": internal_strategy_mode,
                    "internal_entry_price":   internal_entry_price,
                    "internal_entry_time":    internal_entry_time,
                    "trade_high":             trade_high,
                    "trade_low":              trade_low,
                    "bars_held":              bars_held
                })

            # =========================
            # ENTRY LOGIC
            # FIX 10: Only fires during OPEN sessions
            # =========================

            if broker_side is None and signal is not None:

                if session != "OPEN":
                    if session == "MONITOR":
                        print(f"[HOLD] Signal={signal} — waiting for NY open to settle (09:45 ET)")
                    elif session == "CLOSED":
                        print(f"[HOLD] Signal={signal} — outside trading session")
                    elif session == "WEEKEND":
                        print(f"[HOLD] Signal={signal} — weekend, no entries")
                    ib.sleep(POLL_SECONDS)
                    continue

                # FIX 6: no duplicate entries on same bar
                if last_signal_bar_time == signal_row["timestamp"]:
                    ib.sleep(POLL_SECONDS)
                    continue

                print(
                    f"[ENTRY] Regime={regime} Signal={signal} "
                    f"Price≈{current_price:.2f} Qty={QTY}"
                )

                entry_trade        = enter_position(ib, contract, signal, QTY)
                actual_entry_price = get_fill_price(entry_trade, current_price)  # FIX 3

                internal_side          = signal
                internal_strategy_mode = regime
                internal_entry_price   = actual_entry_price
                internal_entry_time    = str(current_bar_time)
                trade_high             = actual_entry_price
                trade_low              = actual_entry_price
                bars_held              = 0
                last_signal_bar_time   = signal_row["timestamp"]

                # FIX 8: IBKR-side protective stop
                dd_guard_pct, _ = get_risk_params(regime)
                stop_price = (
                    actual_entry_price * (1 - dd_guard_pct / 100) if signal == "LONG"
                    else actual_entry_price * (1 + dd_guard_pct / 100)
                )
                open_stop_trade = place_stop_order(ib, contract, signal, QTY, stop_price)

                print(
                    f"[ENTERED] {signal} mode={regime} qty={QTY} "
                    f"fill={actual_entry_price:.2f} stop={stop_price:.2f}"
                )

                save_state({
                    "internal_side":          internal_side,
                    "internal_strategy_mode": internal_strategy_mode,
                    "internal_entry_price":   internal_entry_price,
                    "internal_entry_time":    internal_entry_time,
                    "trade_high":             trade_high,
                    "trade_low":              trade_low,
                    "bars_held":              bars_held
                })

            ib.sleep(POLL_SECONDS)  # FIX 2: ib.sleep everywhere

        except KeyboardInterrupt:
            print("[STOP] Manual stop.")
            break

        # FIX 11: Auto-reconnect on connectivity errors
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")

            if is_connection_error(e):
                print("[RECONNECT] Connection issue detected — attempting reconnect...")
                try:
                    ib = reconnect_ib(ib)
                    contract = get_contract(ib)
                    print("[RECONNECT] Resumed successfully.")
                except RuntimeError as re:
                    print(f"[FATAL] {re}")
                    print("[FATAL] Check TWS is running. Stopping bot.")
                    break
            else:
                ib.sleep(POLL_SECONDS)

    ib.disconnect()
    print("[DONE] Bot stopped and disconnected.")


if __name__ == "__main__":
    main()
