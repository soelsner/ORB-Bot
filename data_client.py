"""Alpaca data layer utilities.

This module centralizes interactions with Alpaca's trading and data APIs,
providing thin wrappers that are resilient to transient rate limits.  All
functions are designed to be idempotent and safe to call repeatedly.
"""
from __future__ import annotations

import datetime as dt
import os
import random
import time
from typing import Dict, Generator, Iterable, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests


class DataClient:
    """Convenience wrapper around Alpaca HTTP endpoints.

    The client intentionally relies on simple HTTP calls (via ``requests``) so
    that it can operate in lightweight environments without the full Alpaca SDK
    installed.  All outbound requests use a shared session and an exponential
    backoff strategy to cope with rate limits or transient server errors.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        trading_base_url: Optional[str] = None,
        data_base_url: Optional[str] = None,
        timezone: str = "America/New_York",
        max_retries: int = 5,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.api_key = api_key or os.getenv("APCA_API_KEY_ID", "")
        self.api_secret = api_secret or os.getenv("APCA_API_SECRET_KEY", "")
        self.trading_base_url = (
            trading_base_url or os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
        )
        # Alpaca's data API uses a different hostname from the trading API.
        self.data_base_url = data_base_url or "https://data.alpaca.markets/v2"
        self.tz = ZoneInfo(timezone)
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.api_secret,
            }
        )

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> Dict:
        """Perform an HTTP request with retry/backoff.

        Idempotent GET/HEAD requests are retried on server errors or HTTP 429
        responses.  Any status code <400 returns parsed JSON; other codes raise
        a ``requests.HTTPError``.
        """

        attempt = 0
        wait = self.backoff_seconds
        while True:
            response = self.session.request(method, url, timeout=30, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                attempt += 1
                if attempt >= self.max_retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else wait
                time.sleep(sleep_for)
                wait = min(wait * 2, 60)
                continue

            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_clock(self) -> Dict:
        """Return market open/close info and session guard details."""

        url = f"{self.trading_base_url}/v2/clock"
        return self._request("GET", url)

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: dt.datetime,
        end: Optional[dt.datetime] = None,
        adjustment: str = "raw",
    ) -> pd.DataFrame:
        """Fetch historical bars and return a normalized DataFrame.

        Parameters mirror Alpaca's bars endpoint.  The returned DataFrame
        contains columns: ``ts``, ``open``, ``high``, ``low``, ``close``, and
        ``volume``.
        """

        end = end or dt.datetime.now(tz=self.tz)
        params = {
            "timeframe": timeframe,
            "start": start.astimezone(dt.timezone.utc).isoformat(),
            "end": end.astimezone(dt.timezone.utc).isoformat(),
            "adjustment": adjustment,
        }
        url = f"{self.data_base_url}/stocks/{symbol}/bars"
        payload = self._request("GET", url, params=params)
        bars = payload.get("bars", [])
        df = pd.DataFrame(
            (
                {
                    "ts": pd.to_datetime(bar.get("t"), utc=True),
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "volume": bar.get("v"),
                }
                for bar in bars
            )
        )
        return df

    def stream_or_poll_5m(
        self,
        symbol: str,
        start: Optional[dt.datetime] = None,
        poll_interval_range: Iterable[float] = (10.0, 15.0),
    ) -> Generator[pd.Series, None, None]:
        """Yield newly closed 5-minute bars via simple polling.

        The generator sleeps between 10–15 seconds (configurable) and only
        yields when a *new* bar close is detected, ensuring idempotent
        downstream consumers.
        """

        last_close: Optional[pd.Timestamp] = None
        start = start or dt.datetime.now(tz=self.tz) - dt.timedelta(minutes=30)

        while True:
            now = dt.datetime.now(tz=self.tz)
            bars = self.get_bars(symbol, "5Min", start, now)
            if not bars.empty:
                latest = bars.iloc[-1]
                if last_close is None or pd.to_datetime(latest["ts"]) > last_close:
                    last_close = pd.to_datetime(latest["ts"])
                    yield latest

            lower, upper = poll_interval_range
            time.sleep(random.uniform(lower, upper))

    def today_1m_since_open(self, symbol: str) -> pd.DataFrame:
        """Return 1-minute bars from 09:30 local time to now."""

        today = dt.datetime.now(tz=self.tz).date()
        session_start = dt.datetime.combine(today, dt.time(9, 30), tzinfo=self.tz)
        return self.get_bars(symbol, "1Min", session_start)

    def account_info(self) -> Dict[str, float]:
        """Return equity and buying power from the account endpoint."""

        url = f"{self.trading_base_url}/v2/account"
        payload = self._request("GET", url)
        return {
            "equity": float(payload.get("equity", 0.0)),
            "buying_power": float(payload.get("buying_power", 0.0)),
        }

    def options_chain(self, symbol: str, date_filter: Optional[str] = None) -> List[Dict]:
        """Return available option contracts with basic greeks."""

        params: Dict[str, str] = {"underlying_symbol": symbol}
        if date_filter:
            params["expiration_date"] = date_filter

        url = f"{self.trading_base_url}/v2/options/contracts"
        payload = self._request("GET", url, params=params)
        contracts = payload.get("contracts", []) or payload.get("data", [])

        normalized: List[Dict] = []
        for contract in contracts:
            normalized.append(
                {
                    "symbol": contract.get("symbol"),
                    "strike": float(contract.get("strike", 0)),
                    "type": contract.get("type") or contract.get("option_type"),
                    "expiry": contract.get("expiration_date") or contract.get("expiry"),
                    "delta": float(contract.get("delta", 0) or 0),
                }
            )
        return normalized

    def option_quote(self, symbol: str) -> Dict[str, float]:
        """Return bid/ask/last quote for an options contract."""

        url = f"{self.data_base_url}/options/{symbol}/quotes/latest"
        payload = self._request("GET", url)
        quote = payload.get("quote") or payload.get("data", {})
        return {
            "bid": float(quote.get("bp", 0) or quote.get("bid_price", 0) or 0),
            "ask": float(quote.get("ap", 0) or quote.get("ask_price", 0) or 0),
            "last": float(quote.get("last", 0) or quote.get("last_price", 0) or 0),
        }


__all__ = [
    "DataClient",
]
