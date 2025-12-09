import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)


@dataclass
class JournalEntry:
    timestamp: str
    symbol: str
    direction: str
    entry: float
    stop: float
    exit: float
    reason: str


class Journal:
    def __init__(self, db_path: Path = Path("journal.db")):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                direction TEXT,
                entry REAL,
                stop REAL,
                exit REAL,
                reason TEXT
            );
            """
        )
        conn.commit()
        conn.close()

    def record(self, entry: JournalEntry) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO trades (timestamp, symbol, direction, entry, stop, exit, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry.timestamp, entry.symbol, entry.direction, entry.entry, entry.stop, entry.exit, entry.reason),
        )
        conn.commit()
        conn.close()

    def export_csv(self, path: Path) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT timestamp,symbol,direction,entry,stop,exit,reason FROM trades").fetchall()
        conn.close()
        import csv  # local import to keep module lightweight

        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "symbol", "direction", "entry", "stop", "exit", "reason"])
            writer.writerows(rows)
        logger.info("Exported journal to %s", path)

    def all_trades(self) -> List[JournalEntry]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT timestamp,symbol,direction,entry,stop,exit,reason FROM trades").fetchall()
        conn.close()
        return [JournalEntry(*row) for row in rows]
