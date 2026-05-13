# bot/connection.py

from ib_insync import IB, Future, Contract, util
import pandas as pd
from config.settings import (
    IB_HOST, IB_PORT, CLIENT_ID,
    SYMBOL, EXPIRY, EXCHANGE, CURRENCY,
    LOOKBACK_DURATION, BAR_SIZE, WHAT_TO_SHOW, USE_RTH
)

RECONNECT_ATTEMPTS = 5
RECONNECT_WAIT_SECONDS = 5


def connect_ib() -> IB:
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID)
    return ib


def reconnect_ib(ib: IB) -> IB:
    """
    Attempt to reconnect after a dropped connection or market data loss.
    Tries up to RECONNECT_ATTEMPTS times with a wait between each.
    Raises RuntimeError if all attempts fail.
    """
    try:
        ib.disconnect()
    except Exception:
        pass

    print(f"[RECONNECT] Connection lost — attempting to reconnect ({RECONNECT_ATTEMPTS} attempts)...")

    for attempt in range(1, RECONNECT_ATTEMPTS + 1):
        try:
            ib.sleep(RECONNECT_WAIT_SECONDS)
            ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID)
            print(f"[RECONNECT] Success on attempt {attempt}")
            return ib
        except Exception as e:
            print(f"[RECONNECT] Attempt {attempt}/{RECONNECT_ATTEMPTS} failed: {e}")

    raise RuntimeError(
        "[RECONNECT] Failed after all attempts. "
        "Check that TWS is running and API is enabled on port 7497."
    )


def get_contract(ib: IB) -> Future:
    contract = Future(
        symbol=SYMBOL,
        lastTradeDateOrContractMonth=EXPIRY,
        exchange=EXCHANGE,
        currency=CURRENCY
    )
    ib.qualifyContracts(contract)
    if not contract.conId:
        raise RuntimeError("Could not qualify MNQ contract. Check EXPIRY in config/settings.py.")
    return contract


def fetch_bars(ib: IB, contract: Contract) -> pd.DataFrame:
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=LOOKBACK_DURATION,
        barSizeSetting=BAR_SIZE,
        whatToShow=WHAT_TO_SHOW,
        useRTH=USE_RTH,
        formatDate=1,
        keepUpToDate=False
    )

    df = util.df(bars)

    if df.empty:
        raise RuntimeError("No bars returned from IBKR.")

    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={
        "date": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume"
    })

    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def get_position_side_and_qty(ib: IB, contract: Contract):
    for pos in ib.positions():
        if pos.contract.conId == contract.conId:
            qty = int(pos.position)
            if qty > 0:
                return "LONG", abs(qty)
            if qty < 0:
                return "SHORT", abs(qty)
    return None, 0
