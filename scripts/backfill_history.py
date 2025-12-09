"""Backfill historical bars for research or replay."""
from datetime import datetime, timedelta

from src.data_client import DataClient


def main():
    client = DataClient()
    end = datetime.utcnow()
    start = end - timedelta(days=5)
    bars = client.get_bars("SPY", "5Min", start, end)
    print(f"Fetched {len(bars)} bars")


if __name__ == "__main__":
    main()
