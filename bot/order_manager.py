# bot/order_manager.py
from ib_insync import IB, Contract, MarketOrder, StopOrder
from config.settings import MNQ_TICK_SIZE

def place_market_order(ib: IB, contract: Contract, action: str, qty: int):
    order = MarketOrder(action, qty, tif='DAY')  # FIX: explicit DAY to prevent Error 10349
    trade = ib.placeOrder(contract, order)
    ib.sleep(2)
    return trade

def get_fill_price(trade, fallback_price: float) -> float:
    """
    FIX: Extract actual fill price from completed trade.
    Original bot used bar close as entry price — this caused wrong
    P&L, MFE/MAE, and exit calculations.
    """
    try:
        if trade and trade.orderStatus.avgFillPrice:
            fill = float(trade.orderStatus.avgFillPrice)
            if fill > 0:
                return fill
    except Exception:
        pass
    return fallback_price

def enter_position(ib: IB, contract: Contract, side: str, qty: int):
    if side == "LONG":
        return place_market_order(ib, contract, "BUY", qty)
    if side == "SHORT":
        return place_market_order(ib, contract, "SELL", qty)
    raise ValueError(f"Invalid side: {side}")

def close_position(ib: IB, contract: Contract, side: str, qty: int):
    if qty <= 0:
        return None
    if side == "LONG":
        return place_market_order(ib, contract, "SELL", qty)
    if side == "SHORT":
        return place_market_order(ib, contract, "BUY", qty)
    return None

def place_stop_order(ib: IB, contract: Contract, side: str, qty: int, stop_price: float):
    """
    Place a protective stop at IBKR level.
    This protects the position if the bot crashes or loses connection.
    """
    action = "SELL" if side == "LONG" else "BUY"
    # Round to nearest valid MNQ tick
    stop_price = round(round(stop_price / MNQ_TICK_SIZE) * MNQ_TICK_SIZE, 2)
    stop = StopOrder(action, qty, stop_price, tif='GTC')  # FIX: GTC so stop survives outside RTH
    stop.outsideRth = True
    trade = ib.placeOrder(contract, stop)
    ib.sleep(1)
    print(f"[STOP ORDER] {action} {qty} @ {stop_price:.2f}")
    return trade

def cancel_order(ib: IB, trade):
    """Cancel an open order safely."""
    if trade is not None:
        try:
            ib.cancelOrder(trade.order)
            ib.sleep(1)
        except Exception:
            pass
