# config/settings.py

# =========================
# IBKR CONNECTION
# =========================
IB_HOST = "127.0.0.1"
IB_PORT = 7497          # 7497 = TWS paper, 7496 = TWS live
CLIENT_ID = 21

# =========================
# CONTRACT
# =========================
SYMBOL = "MNQ"
EXCHANGE = "CME"
CURRENCY = "USD"
EXPIRY = "202606"       # Update manually each roll: 202606, 202609, 202612

# =========================
# DATA
# =========================
BAR_SIZE = "1 min"
LOOKBACK_DURATION = "2 D"
WHAT_TO_SHOW = "TRADES"
USE_RTH = False

# =========================
# TRADING
# =========================
QTY = 1
POLL_SECONDS = 15

# =========================
# MNQ SPECS
# =========================
MNQ_TICK_SIZE = 0.25
MNQ_TICK_VALUE = 0.50

# =========================
# MACD
# =========================
FAST_EMA = 12
SLOW_EMA = 26
SIGNAL_EMA = 9

# =========================
# TREND EMAs
# =========================
EMA_TREND_FAST = 20
EMA_TREND_SLOW = 50

# =========================
# ADX REGIME
# =========================
ADX_PERIOD = 14
ADX_RANGE_MAX = 20.0
ADX_TREND_MIN = 25.0

# =========================
# RANGE MODE
# =========================
RANGE_MACD_MIN_ABS = 2.0
RANGE_DD_GUARD_PCT = 0.20
RANGE_MAX_HOLD_BARS = 6

# =========================
# TREND MODE
# =========================
TREND_DD_GUARD_PCT = 0.35
TREND_MAX_HOLD_BARS = 15

# =========================
# TRAILING TP (TREND only)
# =========================
TREND_TRAIL_ENABLED = True
TREND_TRAIL_START_POINTS = 10.0
TREND_TRAIL_DISTANCE_POINTS = 6.0

# =========================
# FILES
# =========================
TRADE_LOG_FILE = "logs/mnq_trades_log.csv"
STATE_FILE = "bot_state.json"

# =========================
# COSTS
# =========================
COMMISSION_PER_SIDE = 1.32  # Adjust to your actual IBKR rate
