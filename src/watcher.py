import logging
import random
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional

from .journal import Journal

logger = logging.getLogger(__name__)


@dataclass
class PartialTakeConfig:
    enabled: bool = False
    pct_close_at_t1: float = 0.5
    trail_to_be: bool = True
    trail_with_ema21: bool = False


@dataclass
class PositionState:
    symbol: str
    option_symbol: str
    direction: str  # long/short
    stop: float
    t1: float
    t2: float
    t1618: float
    order_id: str
    qty: int
    entry_under_px: float
    trade_id: Optional[int] = None
    entry_ts: Optional[datetime] = None
    runner_qty: Optional[int] = None
    exit1_done: bool = False
    exit2_done: bool = False


class Watcher:
    def __init__(
        self,
        price_provider: Callable[[str], float],
        executor,
        journal: Optional[Journal] = None,
        *,
        kill_switch_pct: float = 3.0,
        partial_take: Optional[PartialTakeConfig] = None,
        poll_seconds_min: int = 2,
        poll_seconds_max: int = 5,
        ema_provider: Optional[Callable[[str], float]] = None,
        risk_limits: Optional[dict] = None,
    ):
        self.price_provider = price_provider
        self.executor = executor
        self.journal = journal
        self.kill_switch_pct = kill_switch_pct
        self.partial_take = partial_take or PartialTakeConfig()
        self.poll_seconds_min = poll_seconds_min
        self.poll_seconds_max = poll_seconds_max
        self.ema_provider = ema_provider
        self.risk_limits = risk_limits or {}

    def _kill_switch_hit(self, entry: float, price: float) -> bool:
        drawdown = (entry - price) / entry * 100
        return drawdown >= self.kill_switch_pct

    def _stop_breached(self, state: PositionState, price: float) -> bool:
        if state.direction == "long":
            return price <= state.stop
        return price >= state.stop

    def _target_hit(self, target: float, direction: str, price: float) -> bool:
        if direction == "long":
            return price >= target
        return price <= target

    def _enforce_limits(self, trade_date: date) -> None:
        if not self.journal:
            return
        limits = self.risk_limits
        trades_taken, mtd_pnl, daily_loss_hit = self.journal.limits_state(trade_date)
        max_trades = limits.get("max_trades_per_day")
        loss_pct = limits.get("daily_loss_pct")
        if daily_loss_hit:
            return
        if max_trades and trades_taken >= max_trades:
            logger.warning("Kill-switch enabled: %s trades taken for %s", trades_taken, trade_date)
            self.journal.mark_daily_loss_hit(trade_date)
        if loss_pct is not None and mtd_pnl <= -abs(loss_pct):
            logger.warning("Kill-switch enabled by PnL for %s: %.2f", trade_date, mtd_pnl)
            self.journal.mark_daily_loss_hit(trade_date)

    def watch(self, state: PositionState, trade_date: Optional[date] = None) -> None:
        trade_date = trade_date or date.today()
        state.runner_qty = state.runner_qty or state.qty
        logger.info("Starting watcher for %s (%s)", state.symbol, state.direction)

        while not state.exit2_done:
            price = self.price_provider(state.symbol)

            if self._kill_switch_hit(state.entry_under_px, price):
                logger.warning("Underlying kill-switch hit for %s", state.symbol)
                self.executor.close_option_market(state.option_symbol)
                self.executor.cancel_children(state.order_id)
                state.exit2_done = True
                if self.journal and state.trade_id:
                    self.journal.record_exit(state.trade_id, datetime.utcnow(), price, exit_leg=2, reason="kill_switch")
                self._enforce_limits(trade_date)
                break

            if self._stop_breached(state, price):
                logger.info("Stop breached for %s at %.2f", state.symbol, price)
                self.executor.close_option_market(state.option_symbol)
                self.executor.cancel_children(state.order_id)
                state.exit2_done = True
                if self.journal and state.trade_id:
                    self.journal.record_exit(state.trade_id, datetime.utcnow(), price, exit_leg=2, reason="underlying_stop")
                break

            if not state.exit1_done and self._target_hit(state.t1, state.direction, price):
                logger.info("T1 reached for %s", state.symbol)
                if self.partial_take.enabled:
                    qty_to_close = max(1, int(state.qty * self.partial_take.pct_close_at_t1))
                    self.executor.close_option_market(state.option_symbol, qty=qty_to_close)
                    state.runner_qty = max(0, state.qty - qty_to_close)
                state.exit1_done = True
                if self.partial_take.trail_to_be:
                    state.stop = max(state.stop, state.entry_under_px)
                if self.partial_take.trail_with_ema21 and self.ema_provider:
                    ema = self.ema_provider(state.symbol)
                    if ema:
                        state.stop = ema if state.direction == "long" else ema
                if self.journal and state.trade_id:
                    self.journal.record_exit(state.trade_id, datetime.utcnow(), price, exit_leg=1, reason="t1")

            if self._target_hit(state.t2, state.direction, price) or self._target_hit(state.t1618, state.direction, price):
                logger.info("Runner target hit for %s", state.symbol)
                self.executor.close_option_market(state.option_symbol)
                self.executor.cancel_children(state.order_id)
                state.exit2_done = True
                if self.journal and state.trade_id:
                    self.journal.record_exit(state.trade_id, datetime.utcnow(), price, exit_leg=2, reason="runner")
                break

            time.sleep(random.uniform(self.poll_seconds_min, self.poll_seconds_max))

        self._enforce_limits(trade_date)
