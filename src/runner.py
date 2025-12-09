import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .data_client import Bar, DataClient
from .executor import Executor
from .fib_orb_engine import (
    ORBBox,
    TradeSignal,
    anchors,
    await_pullback_to,
    compute_orb,
    detect_breakout,
    fib_grid,
    macd,
    stops_targets,
)
from .journal import Journal, TradeRecord
from .notify import notify_email, notify_slack
from .options_selector import OptionsSelector
from .sizer import Sizer
from .utils import AppConfig, now, setup_logging, within_market_hours
from .watcher import PartialTakeConfig, PositionState, Watcher

logger = logging.getLogger(__name__)


class ORBRunner:
    def __init__(
        self,
        config: AppConfig,
        data_client: DataClient,
        selector: OptionsSelector,
        executor: Executor,
        journal: Journal,
    ):
        self.config = config
        self.data_client = data_client
        self.selector = selector
        self.executor = executor
        self.journal = journal
        self.locks: Set[Tuple[str, datetime.date]] = set()

    def _market_open_guard(self, tz) -> bool:
        current = now(tz)
        session_cfg = self.config.settings.get("session", {})
        latest_entry = session_cfg.get("market_latest_entry_et")
        if latest_entry:
            hour, minute = map(int, str(latest_entry).split(":"))
            cutoff = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if current > cutoff:
                logger.info("Past latest entry cutoff; standing down")
                return False
        return within_market_hours(current, tz)

    def run_for_symbol(self, symbol_cfg: Dict[str, str]) -> None:
        tz = self.config.tz()
        if not self._market_open_guard(tz):
            logger.info("Market guard rejected entries for %s", symbol_cfg["ticker"])
            return

        trade_date = now(tz).date()
        symbol = symbol_cfg["ticker"]
        if (symbol, trade_date) in self.locks:
            logger.info("%s already locked for %s", symbol, trade_date)
            return

        trades_taken, _, daily_loss_hit = self.journal.limits_state(trade_date)
        limits_cfg = self.config.settings.get("limits", {})
        max_trades = limits_cfg.get("max_trades_per_day")
        if daily_loss_hit or (max_trades and trades_taken >= max_trades):
            logger.warning("Risk limits preventing new trades for %s", trade_date)
            return

        orb_sequence = self.config.settings.get("session", {}).get("orb_sequence", [30, 15, 60])
        for orb_len in orb_sequence:
            signal, orb_box = self._build_signal(symbol, orb_len, tz)
            if not signal:
                continue

            option = self._select_option(symbol, signal)
            if not option:
                continue

            size = self._size_position(option)
            if not size:
                continue

            order_result = self.executor.enter_with_bracket(
                option_symbol=option.option_symbol,
                qty=size.contracts,
                hard_stop_opt_price=size.hard_stop_price,
                take_profit_opt_price=None,
                trade_date=str(trade_date),
                symbol=symbol,
                direction=signal.direction,
                orb_len=orb_len,
            )
            if not order_result.submitted:
                logger.warning("Order failed for %s: %s", symbol, order_result.reason)
                continue

            trade_id = self._record_trade(signal, orb_box, trade_date, symbol, option.option_symbol, size)
            self._start_watcher(signal, symbol, option.option_symbol, size.contracts, order_result.order_id, trade_id, trade_date)
            self._notify(signal, symbol, order_result.order_id)
            self.locks.add((symbol, trade_date))
            break

    def _build_signal(self, symbol: str, orb_len: int, tz) -> Tuple[Optional[TradeSignal], Optional[ORBBox]]:
        session_start = now(tz).replace(hour=9, minute=30, second=0, microsecond=0)
        end_time = now(tz)
        bars_1m: List[Bar] = self.data_client.get_bars(symbol, "1Min", session_start, end_time)
        bars_5m: List[Bar] = self.data_client.get_bars(symbol, "5Min", session_start, end_time)
        if not bars_1m or not bars_5m:
            return None, None

        try:
            or_high, or_low, or_end = compute_orb(bars_1m, orb_len)
        except ValueError:
            return None, None
        direction_raw, breakout_ts = detect_breakout(bars_5m, or_high, or_low, or_end)
        if not breakout_ts:
            return None, None

        direction_label = "long" if direction_raw == "up" else "short"
        day_high = max(b.high for b in bars_5m)
        day_low = min(b.low for b in bars_5m)
        A, B = anchors(direction_label, day_low, day_high)
        fibs = fib_grid(A, B)
        entry_info, fibs_at_entry = await_pullback_to(
            bars_5m,
            direction_label,
            fibs,
            breakout_ts,
            levels=[0.5, 0.618],
            no_pullback_timeout_min=self.config.settings.get("session", {}).get("no_pullback_timeout_min", 60),
        )
        if entry_info is None:
            return None, None

        level_used, entry_ts, entry_price = entry_info
        try:
            macd_result = macd([b.close for b in bars_5m if b.timestamp <= entry_ts])
        except ValueError:
            macd_result = None
        if macd_result and not self._macd_confirms(direction_label, macd_result):
            return None, None

        stop, targets = stops_targets(direction_label, fibs_at_entry, entry_price, mode="fib")
        reason = f"ORB breakout {direction_label} with fib pullback at {level_used}"
        orb_box = ORBBox(high=or_high, low=or_low, start=bars_1m[0].timestamp, end=or_end)
        signal = TradeSignal(
            direction=direction_label,
            entry=entry_price,
            stop=stop,
            targets=targets,
            reason=reason,
            orb=orb_box,
            entry_time=entry_ts,
            anchor_a=A,
            anchor_b=B,
            entry_level=level_used,
        )
        return signal, orb_box

    def _select_option(self, symbol: str, signal: TradeSignal):
        options_cfg = self.config.settings.get("options", {})
        return self.selector.contracts_for_entry(
            symbol,
            signal.direction,
            signal.entry_time,
            options_cfg.get("expiry_policy", "same_day"),
            options_cfg.get("target_delta", 0.35),
            options_cfg.get("fallback", "ATM"),
        )

    def _size_position(self, option):
        risk_cfg = self.config.settings.get("risk", {})
        sizer = Sizer(
            account_equity=risk_cfg.get("account_equity", 100000),
            portfolio_alloc_pct=risk_cfg.get("portfolio_alloc_pct", 0.25),
            option_hard_stop_pct=risk_cfg.get("option_hard_stop_pct", 0.5),
        )
        return sizer.contracts_for_trade(option.ask, option.ask)

    def _record_trade(
        self,
        signal: TradeSignal,
        orb: ORBBox,
        trade_date: datetime.date,
        symbol: str,
        option_symbol: str,
        size,
    ) -> int:
        t1 = signal.targets[0] if signal.targets else 0
        t2 = signal.targets[1] if len(signal.targets) > 1 else t1
        t1618 = signal.targets[-1] if signal.targets else t2
        trade = TradeRecord(
            trade_date=trade_date,
            symbol=symbol,
            orb_len=int((orb.end - orb.start).total_seconds() // 60),
            direction=signal.direction,
            anchor_a=signal.anchor_a,
            anchor_b=signal.anchor_b,
            entry_level=signal.entry_level,
            entry_ts=signal.entry_time,
            entry_under_px=signal.entry,
            stop_under_px=signal.stop,
            t1_under_px=t1,
            t2_under_px=t2,
            option_sym=option_symbol,
            qty=size.contracts,
            entry_opt_px=size.notional / (size.contracts * 100),
            hard_stop_opt_px=size.hard_stop_price,
            exit_reason=signal.reason,
        )
        return self.journal.record_trade(trade)

    def _start_watcher(
        self,
        signal: TradeSignal,
        symbol: str,
        option_symbol: str,
        qty: int,
        order_id: str,
        trade_id: int,
        trade_date,
    ) -> None:
        watcher_cfg = self.config.settings.get("watcher", {})
        partial_cfg = watcher_cfg.get("partial_take", {})
        watcher = Watcher(
            self.data_client.latest_price,
            executor=self.executor,
            journal=self.journal,
            kill_switch_pct=watcher_cfg.get("kill_switch_pct", 3.0),
            partial_take=PartialTakeConfig(
                enabled=partial_cfg.get("enabled", False),
                pct_close_at_t1=partial_cfg.get("pct_close_at_t1", 0.5),
                trail_to_be=partial_cfg.get("trail_to_be", True),
                trail_with_ema21=partial_cfg.get("trail_with_ema21", False),
            ),
            risk_limits=self.config.settings.get("limits", {}),
        )
        position = PositionState(
            symbol=symbol,
            option_symbol=option_symbol,
            direction=signal.direction,
            stop=signal.stop,
            t1=signal.targets[0],
            t2=signal.targets[1] if len(signal.targets) > 1 else signal.targets[0],
            t1618=signal.targets[-1],
            order_id=order_id or "",
            qty=qty,
            entry_under_px=signal.entry,
            trade_id=trade_id,
            entry_ts=signal.entry_time,
        )
        watcher.watch(position, trade_date=trade_date)

    def _notify(self, signal: TradeSignal, symbol: str, order_id: str) -> None:
        notifications = self.config.settings.get("notifications", {})
        notify_slack(notifications.get("slack_webhook", ""), f"{symbol} {signal.direction} signal sent")
        notify_email(
            notifications.get("email_to", ""),
            notifications.get("from_email", ""),
            f"{symbol} {signal.direction} signal submitted as order {order_id}",
        )

    @staticmethod
    def _macd_confirms(direction: str, macd_result) -> bool:
        if direction == "long":
            return macd_result.macd >= macd_result.signal and macd_result.histogram >= 0
        return macd_result.macd <= macd_result.signal and macd_result.histogram <= 0


def main(settings_path: str = "config/settings.yml", symbols_path: str = "config/symbols.yml") -> None:
    config = AppConfig.load(Path(settings_path), Path(symbols_path))
    setup_logging(config.settings)
    data_client = DataClient()
    runner = ORBRunner(
        config=config,
        data_client=data_client,
        selector=OptionsSelector(data_client),
        executor=Executor(client=None),
        journal=Journal(),
    )
    for symbol_cfg in config.symbols.get("symbols", []):
        runner.run_for_symbol(symbol_cfg)


if __name__ == "__main__":
    main()
