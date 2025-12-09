# ORB + Fib Options Bot

An opinionated, build-ready scaffold for an Opening Range Breakout (ORB) + Fibonacci pullback options strategy on Alpaca. The system tracks a configurable ORB window, waits for a full-bar breakout, enters on 0.5/0.618 pullbacks with MACD confluence, and manages positions with bracket protection and an underlying watcher.

## Layout
```
orb-fib-bot/
  config/
    settings.yml          # session, risk, options, notifications
    symbols.yml           # tickers to scan
  src/
    runner.py             # entry point
    data_client.py        # Alpaca data wrapper (mock by default)
    indicators.py         # MACD, swing helpers
    fib_orb_engine.py     # ORB + Fib breakout logic
    options_selector.py   # expiry/strike selection
    sizer.py              # position sizing
    executor.py           # order placement (mock-friendly)
    watcher.py            # underlying monitoring
    journal.py            # SQLite trade log
    notify.py             # Slack/Email hooks (stubs)
    utils.py              # config + logging helpers
  tests/
    test_engine.py        # ORB/Fib engine coverage
    test_sizer.py
    test_executor.py
  scripts/
    backfill_history.py   # quick bar fetch demo
    paper_reset.py        # placeholder reset script
  Dockerfile
  requirements.txt
```

## Quickstart
1. Install deps: `pip install -r requirements.txt`
2. Configure symbols and risk in `config/settings.yml` and `config/symbols.yml` (JSON syntax that remains valid YAML).
3. Run the intraday loop (mocked data provider by default):
   ```bash
   python -m src.runner
   ```
4. Execute tests:
   ```bash
   pytest
   ```

## Notes
- The Alpaca client hooks are intentionally thin so you can inject a real provider.
- Signals require ORB breakout, Fib retest (0.5/0.618), and MACD agreement; otherwise, the bot stays flat.
- Journal entries are stored in `journal.db` and can be exported to CSV.
