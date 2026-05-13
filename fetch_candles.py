#!/usr/bin/env python3
"""
fetch_candles.py
────────────────
Fetches historical 1-minute candle data for MNQ from IBKR
and saves it to a CSV file for analysis.

Usage:
    python fetch_candles.py              # fetches today
    python fetch_candles.py 2026-05-13   # fetches a specific date
    python fetch_candles.py 3            # fetches last 3 days

Output:
    logs/candles_YYYYMMDD.csv
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# ── Add bot path ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.connection import connect_ib, get_contract
from ib_insync import util
from config.settings import EXPIRY, EXCHANGE, CURRENCY

# ── Parse argument ───────────────────────────────────────────
def parse_args():
    if len(sys.argv) < 2:
        # Default: today
        return 1, None
    arg = sys.argv[1]
    # Check if it's a date like 2026-05-13
    try:
        datetime.strptime(arg, "%Y-%m-%d")
        return 1, arg
    except ValueError:
        pass
    # Check if it's a number of days
    try:
        return int(arg), None
    except ValueError:
        print(f"[ERROR] Invalid argument: {arg}")
        print("Usage: python fetch_candles.py [YYYY-MM-DD | days]")
        sys.exit(1)

def main():
    days, specific_date = parse_args()

    # ── Connect ──────────────────────────────────────────────
    print("[INFO] Connecting to IBKR...")
    ib = connect_ib()
    contract = get_contract(ib)
    print(f"[INFO] Contract: {contract.localSymbol}")

    # ── Build request parameters ─────────────────────────────
    if specific_date:
        # Fetch just that day — end at midnight of next day
        end_dt = datetime.strptime(specific_date, "%Y-%m-%d") + timedelta(days=1)
        end_str = end_dt.strftime("%Y%m%d %H:%M:%S")
        duration = "1 D"
        label = specific_date.replace("-", "")
    else:
        end_str = ""  # empty = now
        duration = f"{days} D"
        label = datetime.now().strftime("%Y%m%d")
        if days > 1:
            label = f"{(datetime.now() - timedelta(days=days)).strftime('%Y%m%d')}_to_{label}"

    print(f"[INFO] Fetching {duration} of 1-min candles...")

    # ── Fetch bars ───────────────────────────────────────────
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=end_str,
        durationStr=duration,
        barSizeSetting="1 min",
        whatToShow="TRADES",
        useRTH=False,
        formatDate=1,
        keepUpToDate=False
    )

    if not bars:
        print("[ERROR] No data returned. Is TWS running?")
        ib.disconnect()
        return

    # ── Convert to DataFrame ─────────────────────────────────
    df = util.df(bars)
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"date": "timestamp"})
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    # ── Add useful columns ───────────────────────────────────
    df["et_time"] = df["timestamp"].dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    df["change"]  = (df["close"] - df["open"]).round(2)
    df["range"]   = (df["high"] - df["low"]).round(2)

    # ── Save to CSV ──────────────────────────────────────────
    os.makedirs("logs", exist_ok=True)
    out_file = f"logs/candles_{label}.csv"
    df.to_csv(out_file, index=False)

    print(f"[OK] {len(df)} candles saved to {out_file}")

    # ── Quick summary ────────────────────────────────────────
    print("\n── Day Summary ──────────────────────────────")
    print(f"  First candle : {df.iloc[0]['timestamp']}  open={df.iloc[0]['open']}")
    print(f"  Last candle  : {df.iloc[-1]['timestamp']}  close={df.iloc[-1]['close']}")
    print(f"  Day high     : {df['high'].max()}")
    print(f"  Day low      : {df['low'].min()}")
    print(f"  Day range    : {(df['high'].max() - df['low'].min()):.2f} points")

    # ── Show after-session candles (after 15:45 ET) ──────────
    after = df[df["et_time"] >= "15:45"].copy()
    if not after.empty:
        print(f"\n── After 15:45 ET ({len(after)} candles) ──────────")
        print(f"  Price at 15:45 : {after.iloc[0]['open']:.2f}")
        print(f"  High after     : {after['high'].max():.2f}  (+{after['high'].max() - after.iloc[0]['open']:.2f})")
        print(f"  Low after      : {after['low'].min():.2f}  ({after['low'].min() - after.iloc[0]['open']:.2f})")
        print(f"  Close of day   : {after.iloc[-1]['close']:.2f}")
        print(f"\n  Top 5 biggest moves after session:")
        after["abs_change"] = after["change"].abs()
        top5 = after.nlargest(5, "abs_change")[["et_time", "open", "high", "low", "close", "change", "range"]]
        print(top5.to_string(index=False))

    print("\n" + "─" * 48)
    ib.disconnect()
    print(f"[DONE] Data saved to {out_file}")

if __name__ == "__main__":
    main()
