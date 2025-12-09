import logging
from datetime import datetime, timedelta
from pathlib import Path

from .data_client import DataClient
from .fib_orb_engine import FibOrbEngine
from .options_selector import OptionsSelector
from .sizer import Sizer
from .executor import Executor
from .journal import Journal, JournalEntry
from .notify import notify_email, notify_slack
from .utils import AppConfig, now, setup_logging, within_market_hours

logger = logging.getLogger(__name__)


def main(settings_path: str = "config/settings.yml", symbols_path: str = "config/symbols.yml") -> None:
    config = AppConfig.load(Path(settings_path), Path(symbols_path))
    setup_logging(config.settings)
    tz = config.tz()

    data_client = DataClient()
    engine = FibOrbEngine(
        orb_minutes=config.settings.get("session", {}).get("orb_minutes", 30),
        breakout_close_minutes=config.settings.get("session", {}).get("breakout_close_minutes", 5),
    )
    selector = OptionsSelector(
        data_client,
        min_delta=config.settings.get("options", {}).get("min_delta", 0.3),
        max_delta=config.settings.get("options", {}).get("max_delta", 0.6),
        days_to_expiry=config.settings.get("options", {}).get("days_to_expiry", 5),
    )
    executor = Executor(client=None)
    journal = Journal()

    for symbol_cfg in config.symbols.get("symbols", []):
        symbol = symbol_cfg["ticker"]
        _process_symbol(symbol, tz, data_client, engine, selector, executor, journal, config)


def _process_symbol(symbol, tz, data_client, engine, selector, executor, journal, config):
    if not within_market_hours(now(tz), tz):
        logger.info("Outside market hours for %s", symbol)
        return

    end = now(tz)
    start = end - timedelta(hours=6)
    bars = data_client.get_bars(symbol, config.settings.get("session", {}).get("fib_timeframe", "5Min"), start, end)
    signal = engine.evaluate(bars)
    if not signal:
        logger.info("No signal for %s", symbol)
        return

    option = selector.choose(symbol, signal.direction, end)
    if not option:
        logger.warning("No option candidate for %s", symbol)
        return

    sizer = Sizer(
        portfolio_value=100000,  # placeholder until hooked into broker account
        risk_pct=config.settings.get("risk", {}).get("portfolio_risk_pct", 1.0),
        stop_buffer_pct=config.settings.get("risk", {}).get("stop_buffer_pct", 0.0),
    )
    size = sizer.contracts_for_trade(option.mid, signal.stop, signal.entry)
    if not size:
        logger.warning("Sizing rejected for %s", symbol)
        return

    order_result = executor.place_bracket(symbol, size.contracts, signal.entry, signal.stop, signal.targets)
    if not order_result.submitted:
        logger.warning("Order failed for %s: %s", symbol, order_result.reason)
        return

    journal.record(
        JournalEntry(
            timestamp=str(end),
            symbol=symbol,
            direction=signal.direction,
            entry=signal.entry,
            stop=signal.stop,
            exit=0.0,
            reason=signal.reason,
        )
    )

    notify_slack(config.settings.get("notifications", {}).get("slack_webhook", ""), f"{symbol} {signal.direction} signal sent")
    notify_email(
        config.settings.get("notifications", {}).get("email_to", ""),
        config.settings.get("notifications", {}).get("from_email", ""),
        f"{symbol} {signal.direction} signal submitted as order {order_result.order_id}",
    )


if __name__ == "__main__":
    main()
