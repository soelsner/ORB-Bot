# ORB-Bot
Automated ORB Breakout + Fibonacci Pullback + MACD Confluence Strategy (Alpaca Options)

This project implements a fully automated, production-grade trading system that executes the Opening Range Breakout (ORB) strategy combined with Fibonacci pullback entries and MACD confluence, using Alpaca’s Options API.

It is designed to mirror the workflow described by an ORB + Fib trader who has traded this system profitably for years.

The bot automatically:

Builds the 15m / 30m / 60m Opening Range

Confirms breakout with a full 5-minute candle close beyond OR

Draws Fibonacci levels on the 5-minute chart

Waits for a pullback to 0.50 or 0.618 retracement

Confirms with MACD curl (momentum shift)

Selects the best options contract by expiry & delta

Sizes the position using % of portfolio allocation

Places Alpaca market bracket orders with a hard stop

Monitors the underlying for exits at:

HOD/LOD retest

Fib extensions (1.272 / 1.618)

Or R-multiple (optional)

Journals all trades into SQLite

Provides optional Slack/email alerts

Enforces daily loss limits, max trades per day, and automatic kill-switches
