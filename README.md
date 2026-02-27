Gate Tick Timer
A lightweight desktop utility for monitoring real-time trade ticks on Gate.io (Spot) using ccxt.
The app measures the time interval between consecutive BUY/SELL trades and displays them in a minimal, high-contrast interface with a built-in stopwatch.

🚀 Features
Monitor any Gate.io spot trading pair (e.g. CTP/USDT)
Stopwatch automatically starts on the first detected trade
Displays interval between consecutive trades
Filters only real BUY/SELL trades
Duplicate tick protection
Highlights identical time intervals
Dark minimal trading-style UI
Lightweight and responsive (threaded polling)

🖥️ Interface
Input field for trading pair
Large stopwatch display
Interval since last tick

Table with:
Interval
Side (BUY/SELL)

📦 Requirements
Python 3.9+
ccxt

Install dependencies:
pip install ccxt
▶️ Run
python gate_tick_timer.py
Enter a trading pair (example: CTP/USDT) and press Start.
The stopwatch begins on the first detected trade.

⚠️ Notes
Uses REST polling (not WebSocket).
Poll interval is ~250ms.
Intended for analytical and monitoring purposes only.
