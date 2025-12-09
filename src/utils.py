import json
import logging
import logging.config
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from zoneinfo import ZoneInfo


@dataclass
class AppConfig:
    settings: Dict[str, Any]
    symbols: Dict[str, Any]

    @classmethod
    def load(cls, settings_path: Path, symbols_path: Path) -> "AppConfig":
        return cls(settings=_load_yaml(settings_path), symbols=_load_yaml(symbols_path))

    def tz(self) -> ZoneInfo:
        tz_name = self.settings.get("session", {}).get("timezone", "America/New_York")
        return ZoneInfo(tz_name)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file missing: {path}")
    with path.open() as f:
        content = f.read()
    try:
        import yaml  # type: ignore

        return yaml.safe_load(content) or {}
    except Exception:
        # Fallback for environments without PyYAML: assume JSON-compatible payload
        return json.loads(content)


def setup_logging(config: Dict[str, Any]) -> None:
    level = config.get("logging", {}).get("level", "INFO").upper()
    log_file = Path(config.get("logging", {}).get("log_file", "logs/orb_fib_bot.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file),
        ],
    )


def now(tz: Optional[pytz.BaseTzInfo] = None) -> datetime:
    tzinfo = tz or ZoneInfo("UTC")
    return datetime.now(tzinfo)


def within_market_hours(dt: datetime, tz) -> bool:
    local_dt = dt.astimezone(tz)
    if local_dt.weekday() >= 5:
        return False
    market_open = local_dt.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = local_dt.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= local_dt <= market_close
