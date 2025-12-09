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
    selector = OptionsSelector(data_client)
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

    options_cfg = config.settings.get("options", {})
    option = selector.contracts_for_entry(
        symbol,
        signal.direction,
        end,
        options_cfg.get("expiry_policy", "same_day"),
        options_cfg.get("target_delta", 0.35),
        options_cfg.get("fallback", "ATM"),
    )
    if not option:
        logger.warning("No option candidate for %s", symbol)
        return

    sizer = Sizer(
        account_equity=100000,  # placeholder until hooked into broker account
        portfolio_alloc_pct=config.settings.get("risk", {}).get("portfolio_alloc_pct", 0.25),
        option_hard_stop_pct=config.settings.get("risk", {}).get("option_hard_stop_pct", 0.5),
    )
    size = sizer.contracts_for_trade(option.ask, option.ask)
    if not size:
        logger.warning("Sizing rejected for %s", symbol)
        return

    order_result = executor.enter_with_bracket(
        option_symbol=option.option_symbol,
        qty=size.contracts,
        hard_stop_opt_price=size.hard_stop_price,
        take_profit_opt_price=None,
        trade_date=str(end.date()),
        symbol=symbol,
        direction=signal.direction,
        orb_len=engine.orb_minutes,
    )
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
