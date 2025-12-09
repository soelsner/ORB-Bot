import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    submitted: bool
    order_id: Optional[str] = None
    reason: str = ""


class Executor:
    def __init__(self, client):
        self.client = client

    def place_bracket(self, symbol: str, contracts: int, entry: float, stop: float, targets) -> OrderResult:
        if not self.client:
            logger.warning("No trading client configured; skipping order")
            return OrderResult(submitted=False, reason="no_client")
        try:
            order = self.client.place_bracket_order(symbol, contracts, entry, stop, targets)
            return OrderResult(submitted=True, order_id=order.get("id"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to place order: %s", exc)
            return OrderResult(submitted=False, reason=str(exc))
