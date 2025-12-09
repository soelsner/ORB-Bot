import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

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


@dataclass
class TradeRecord:
    trade_date: date
    symbol: str
    orb_len: int
    direction: str
    anchor_a: float
    anchor_b: float
    entry_level: float
    entry_ts: datetime
    entry_under_px: float
    stop_under_px: float
    t1_under_px: float
    t2_under_px: float
    option_sym: str
    qty: int
    entry_opt_px: float
    hard_stop_opt_px: float
    exit_reason: str = ""
    notes: str = ""


class Journal:
    def __init__(self, db_path: Path = Path("journal.db")):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                symbol TEXT,
                orb_len INTEGER,
                direction TEXT,
                A REAL,
                B REAL,
                entry_level REAL,
                entry_ts TEXT,
                entry_under_px REAL,
                stop_under_px REAL,
                t1_under_px REAL,
                t2_under_px REAL,
                option_sym TEXT,
                qty INTEGER,
                entry_opt_px REAL,
                hard_stop_opt_px REAL,
                exit1_ts TEXT,
                exit1_px REAL,
                exit2_ts TEXT,
                exit2_px REAL,
                pnl_usd REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                notes TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS limits_state (
                date TEXT PRIMARY KEY,
                trades_taken INTEGER DEFAULT 0,
                mtd_pnl REAL DEFAULT 0,
                daily_loss_hit INTEGER DEFAULT 0
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                ts TEXT,
                equity_usd REAL
            );
            """
        )
        conn.commit()
        conn.close()

    def record(self, entry: JournalEntry) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO trades (date, symbol, direction, entry_level, stop_under_px, exit_reason) VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry.timestamp.split(" ")[0],
                entry.symbol,
                entry.direction,
                entry.entry,
                entry.stop,
                entry.reason,
            ),
        )
        conn.commit()
        conn.close()

    def record_trade(self, trade: TradeRecord) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            INSERT INTO trades (
                date, symbol, orb_len, direction, A, B, entry_level, entry_ts, entry_under_px,
                stop_under_px, t1_under_px, t2_under_px, option_sym, qty, entry_opt_px,
                hard_stop_opt_px, exit_reason, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.trade_date.isoformat(),
                trade.symbol,
                trade.orb_len,
                trade.direction,
                trade.anchor_a,
                trade.anchor_b,
                trade.entry_level,
                trade.entry_ts.isoformat(),
                trade.entry_under_px,
                trade.stop_under_px,
                trade.t1_under_px,
                trade.t2_under_px,
                trade.option_sym,
                trade.qty,
                trade.entry_opt_px,
                trade.hard_stop_opt_px,
                trade.exit_reason,
                trade.notes,
            ),
        )
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info("Recorded trade %s for %s", trade_id, trade.symbol)
        self._increment_trades_taken(trade.trade_date)
        return trade_id

    def record_exit(
        self,
        trade_id: int,
        exit_ts: datetime,
        exit_price: float,
        exit_leg: int,
        *,
        pnl_usd: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        column_ts = "exit1_ts" if exit_leg == 1 else "exit2_ts"
        column_px = "exit1_px" if exit_leg == 1 else "exit2_px"
        set_reason = ", exit_reason = ?" if reason else ""
        query = f"UPDATE trades SET {column_ts} = ?, {column_px} = ?"
        params: List[object] = [exit_ts.isoformat(), exit_price]
        if pnl_usd is not None:
            query += ", pnl_usd = ?"
            params.append(pnl_usd)
        if pnl_pct is not None:
            query += ", pnl_pct = ?"
            params.append(pnl_pct)
        if reason:
            params.append(reason)
        query += set_reason
        query += " WHERE trade_id = ?"
        params.append(trade_id)
        conn = sqlite3.connect(self.db_path)
        conn.execute(query, params)
        conn.commit()
        conn.close()

    def export_csv(self, path: Path) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """
            SELECT trade_id,date,symbol,orb_len,direction,A,B,entry_level,entry_ts,entry_under_px,
                   stop_under_px,t1_under_px,t2_under_px,option_sym,qty,entry_opt_px,hard_stop_opt_px,
                   exit1_ts,exit1_px,exit2_ts,exit2_px,pnl_usd,pnl_pct,exit_reason,notes
            FROM trades
            ORDER BY trade_id
            """
        ).fetchall()
        conn.close()
        import csv  # local import to keep module lightweight

        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "trade_id",
                    "date",
                    "symbol",
                    "orb_len",
                    "direction",
                    "A",
                    "B",
                    "entry_level",
                    "entry_ts",
                    "entry_under_px",
                    "stop_under_px",
                    "t1_under_px",
                    "t2_under_px",
                    "option_sym",
                    "qty",
                    "entry_opt_px",
                    "hard_stop_opt_px",
                    "exit1_ts",
                    "exit1_px",
                    "exit2_ts",
                    "exit2_px",
                    "pnl_usd",
                    "pnl_pct",
                    "exit_reason",
                    "notes",
                ]
            )
            writer.writerows(rows)
        logger.info("Exported journal to %s", path)

    def all_trades(self) -> List[JournalEntry]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT entry_ts as timestamp,symbol,direction,entry_level as entry,stop_under_px as stop,exit2_px as exit,exit_reason as reason FROM trades").fetchall()
        conn.close()
        return [JournalEntry(*row) for row in rows]

    def limits_state(self, for_date: date) -> Tuple[int, float, bool]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT trades_taken, mtd_pnl, daily_loss_hit FROM limits_state WHERE date = ?",
            (for_date.isoformat(),),
        ).fetchone()
        conn.close()
        if not row:
            return 0, 0.0, False
        trades_taken, mtd_pnl, daily_loss_hit = row
        return int(trades_taken), float(mtd_pnl), bool(daily_loss_hit)

    def mark_daily_loss_hit(self, for_date: date) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO limits_state (date, daily_loss_hit) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET daily_loss_hit=1
            """,
            (for_date.isoformat(),),
        )
        conn.commit()
        conn.close()

    def update_mtd_pnl(self, for_date: date, pnl_delta: float) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO limits_state (date, trades_taken, mtd_pnl, daily_loss_hit)
            VALUES (?, 0, ?, 0)
            ON CONFLICT(date) DO UPDATE SET mtd_pnl = mtd_pnl + excluded.mtd_pnl
            """,
            (for_date.isoformat(), pnl_delta),
        )
        conn.commit()
        conn.close()

    def _increment_trades_taken(self, for_date: date) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO limits_state (date, trades_taken, mtd_pnl, daily_loss_hit)
            VALUES (?, 1, 0, 0)
            ON CONFLICT(date) DO UPDATE SET trades_taken = trades_taken + 1
            """,
            (for_date.isoformat(),),
        )
        conn.commit()
        conn.close()

    def log_equity_snapshot(self, equity_usd: float, ts: Optional[datetime] = None) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO equity_snapshots (ts, equity_usd) VALUES (?, ?)",
            ((ts or datetime.utcnow()).isoformat(), equity_usd),
        )
        conn.commit()
        conn.close()

