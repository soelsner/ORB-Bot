import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class WatchDecision:
    action: str  # hold/scale/exit
    reason: str


class Watcher:
    def __init__(self, price_provider: Callable[[str], float], kill_switch_pct: float = 3.0):
        self.price_provider = price_provider
        self.kill_switch_pct = kill_switch_pct

    def evaluate(self, symbol: str, entry: float) -> Optional[WatchDecision]:
        price = self.price_provider(symbol)
        drawdown = (entry - price) / entry * 100
        if drawdown >= self.kill_switch_pct:
            logger.warning("Kill-switch hit for %s at %.2f%%", symbol, drawdown)
            return WatchDecision(action="exit", reason="kill_switch")
        if price >= entry * 1.5:
            return WatchDecision(action="scale", reason="runner_protect")
        return WatchDecision(action="hold", reason="normal")
