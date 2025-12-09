import logging
from dataclasses import dataclass
from typing import Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    submitted: bool
    order_id: Optional[str] = None
    reason: str = ""


class Executor:
    def __init__(self, client):
        self.client = client
        self._submitted_keys: Set[Tuple[str, str, str, int]] = set()

    def enter_with_bracket(
        self,
        option_symbol: str,
        qty: int,
        hard_stop_opt_price: float,
        take_profit_opt_price: Optional[float],
        *,
        trade_date: str,
        symbol: str,
        direction: str,
        orb_len: int,
    ) -> OrderResult:
        if not self.client:
            logger.warning("No trading client configured; skipping order")
            return OrderResult(submitted=False, reason="no_client")

        key = (trade_date, symbol, direction, orb_len)
        if key in self._submitted_keys:
            logger.info("Duplicate order detected for %s on %s", symbol, trade_date)
            return OrderResult(submitted=False, reason="duplicate")

        try:
            order_kwargs = {
                "symbol": option_symbol,
                "qty": qty,
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "order_class": "bracket",
                "stop_loss": {"stop_price": hard_stop_opt_price},
            }
            if take_profit_opt_price is not None:
                order_kwargs["take_profit"] = {"limit_price": take_profit_opt_price}

            order = self.client.submit_order(**order_kwargs)
            order_id = order.get("id") if isinstance(order, dict) else None
            self._submitted_keys.add(key)
            return OrderResult(submitted=True, order_id=order_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to place order: %s", exc)
            return OrderResult(submitted=False, reason=str(exc))

    def close_option_market(self, symbol: str, qty: Optional[int] = None) -> None:
        if not self.client:
            logger.warning("No trading client configured; cannot close %s", symbol)
            return
        try:
            kwargs = {"symbol": symbol, "type": "market"}
            if qty is not None:
                kwargs["qty"] = qty
            self.client.close_position(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to close %s: %s", symbol, exc)

    def cancel_children(self, order_id: str) -> None:
        if not self.client:
            logger.warning("No trading client configured; cannot cancel children for %s", order_id)
            return
        try:
            self.client.cancel_child_orders(order_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to cancel children for %s: %s", order_id, exc)
