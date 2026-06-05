"""SQLite 数据访问层 — 守基宝交易辅助系统"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from services.models import Fund, Position, Trade, UserConfig

if TYPE_CHECKING:
    pass

# 数据库默认路径
_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DB_DIR / "winwin.db"


class DatabaseManager:
    """SQLite 数据库管理器，封装所有表的 CRUD 操作。"""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ==================== 连接管理 ====================

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_db(self) -> None:
        """初始化数据库，创建所有表。"""
        self.conn.executescript(_CREATE_TABLES_SQL)
        self.conn.commit()

    # ==================== Fund CRUD ====================

    def add_fund(self, fund: Fund) -> int:
        """添加基金，返回新插入的 id。"""
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """INSERT INTO fund (code, name, fund_type, main_ratio, swing_ratio,
               opportunity_line, middle_line, danger_line,
               per_share_amount, total_shares_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fund.code, fund.name, fund.fund_type,
                fund.main_ratio, fund.swing_ratio,
                fund.opportunity_line, fund.middle_line, fund.danger_line,
                fund.per_share_amount, fund.total_shares_count,
                now, now,
            ),
        )
        self.conn.commit()
        fund_id = cursor.lastrowid or 0
        # 同时创建对应的 Position 记录
        self.conn.execute(
            "INSERT INTO position (fund_id, updated_at) VALUES (?, ?)",
            (fund_id, now),
        )
        self.conn.commit()
        return fund_id

    def get_fund(self, fund_id: int) -> Fund | None:
        """按 id 获取基金。"""
        row = self.conn.execute("SELECT * FROM fund WHERE id = ?", (fund_id,)).fetchone()
        return self._row_to_fund(row) if row else None

    def get_fund_by_code(self, code: str) -> Fund | None:
        """按基金代码获取。"""
        row = self.conn.execute("SELECT * FROM fund WHERE code = ?", (code,)).fetchone()
        return self._row_to_fund(row) if row else None

    def get_all_funds(self) -> list[Fund]:
        """获取所有基金。"""
        rows = self.conn.execute("SELECT * FROM fund ORDER BY id").fetchall()
        return [self._row_to_fund(r) for r in rows]

    def update_fund(self, fund: Fund) -> None:
        """更新基金配置。"""
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """UPDATE fund SET name=?, fund_type=?, main_ratio=?, swing_ratio=?,
               opportunity_line=?, middle_line=?, danger_line=?,
               per_share_amount=?, total_shares_count=?, updated_at=?
               WHERE id=?""",
            (
                fund.name, fund.fund_type, fund.main_ratio, fund.swing_ratio,
                fund.opportunity_line, fund.middle_line, fund.danger_line,
                fund.per_share_amount, fund.total_shares_count, now,
                fund.id,
            ),
        )
        self.conn.commit()

    def delete_fund(self, fund_id: int) -> None:
        """删除基金及其关联的持仓和交易记录。"""
        self.conn.execute("DELETE FROM trade WHERE fund_id = ?", (fund_id,))
        self.conn.execute("DELETE FROM position WHERE fund_id = ?", (fund_id,))
        self.conn.execute("DELETE FROM fund WHERE id = ?", (fund_id,))
        self.conn.commit()

    def get_fund_count(self) -> int:
        """获取基金数量。"""
        row = self.conn.execute("SELECT COUNT(*) FROM fund").fetchone()
        return row[0] if row else 0

    # ==================== Position CRUD ====================

    def get_position(self, fund_id: int) -> Position | None:
        """获取基金持仓状态。"""
        row = self.conn.execute(
            "SELECT * FROM position WHERE fund_id = ?", (fund_id,)
        ).fetchone()
        return self._row_to_position(row) if row else None

    def update_position(self, pos: Position) -> None:
        """更新持仓状态。"""
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """UPDATE position SET total_shares=?, total_invested=?,
               main_shares=?, swing_shares=?, anchor_nav=?, highest_nav=?,
               consecutive_buy=?, consecutive_sell=?, current_strategy=?, updated_at=?
               WHERE fund_id=?""",
            (
                pos.total_shares, pos.total_invested,
                pos.main_shares, pos.swing_shares,
                pos.anchor_nav, pos.highest_nav,
                pos.consecutive_buy, pos.consecutive_sell,
                pos.current_strategy, now,
                pos.fund_id,
            ),
        )
        self.conn.commit()

    # ==================== Trade CRUD ====================

    def add_trade(self, trade: Trade) -> int:
        """添加交易记录，返回 id。"""
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """INSERT INTO trade (fund_id, trade_date, trade_type, strategy_type,
               nav, amount, shares, trigger_reason, confirmed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.fund_id, trade.trade_date, trade.trade_type,
                trade.strategy_type, trade.nav, trade.amount, trade.shares,
                trade.trigger_reason, trade.confirmed, now,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def get_trades(self, fund_id: int, limit: int = 50) -> list[Trade]:
        """获取基金交易记录（最新在前）。"""
        rows = self.conn.execute(
            "SELECT * FROM trade WHERE fund_id = ? ORDER BY trade_date DESC, id DESC LIMIT ?",
            (fund_id, limit),
        ).fetchall()
        return [self._row_to_trade(r) for r in rows]

    def get_all_trades(self, fund_id: int) -> list[Trade]:
        """获取基金全部交易记录（时间正序）。"""
        rows = self.conn.execute(
            "SELECT * FROM trade WHERE fund_id = ? ORDER BY trade_date ASC, id ASC",
            (fund_id,),
        ).fetchall()
        return [self._row_to_trade(r) for r in rows]

    def update_trade(self, trade: Trade) -> None:
        """更新交易记录。"""
        self.conn.execute(
            """UPDATE trade SET trade_date=?, trade_type=?, strategy_type=?,
               nav=?, amount=?, shares=?, trigger_reason=?, confirmed=?
               WHERE id=?""",
            (
                trade.trade_date, trade.trade_type, trade.strategy_type,
                trade.nav, trade.amount, trade.shares,
                trade.trigger_reason, trade.confirmed, trade.id,
            ),
        )
        self.conn.commit()

    def delete_trade(self, trade_id: int) -> None:
        """删除交易记录。"""
        self.conn.execute("DELETE FROM trade WHERE id = ?", (trade_id,))
        self.conn.commit()

    def get_last_trade(self, fund_id: int) -> Trade | None:
        """获取最近一笔已确认的交易。"""
        row = self.conn.execute(
            """SELECT * FROM trade WHERE fund_id = ? AND confirmed = 1
               ORDER BY trade_date DESC, id DESC LIMIT 1""",
            (fund_id,),
        ).fetchone()
        return self._row_to_trade(row) if row else None

    # ==================== UserConfig CRUD ====================

    def get_config(self, key: str, default: str = "") -> str:
        """获取用户配置。"""
        row = self.conn.execute(
            "SELECT value FROM user_config WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_config(self, key: str, value: str) -> None:
        """设置用户配置（insert or replace）。"""
        self.conn.execute(
            "INSERT OR REPLACE INTO user_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    # ==================== 行映射辅助 ====================

    @staticmethod
    def _row_to_fund(row: sqlite3.Row) -> Fund:
        return Fund(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            fund_type=row["fund_type"] or "",
            main_ratio=row["main_ratio"],
            swing_ratio=row["swing_ratio"],
            opportunity_line=row["opportunity_line"],
            middle_line=row["middle_line"],
            danger_line=row["danger_line"],
            per_share_amount=row["per_share_amount"],
            total_shares_count=row["total_shares_count"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> Position:
        return Position(
            id=row["id"],
            fund_id=row["fund_id"],
            total_shares=row["total_shares"],
            total_invested=row["total_invested"],
            main_shares=row["main_shares"],
            swing_shares=row["swing_shares"],
            anchor_nav=row["anchor_nav"],
            highest_nav=row["highest_nav"],
            consecutive_buy=row["consecutive_buy"],
            consecutive_sell=row["consecutive_sell"],
            current_strategy=row["current_strategy"] or "none",
            updated_at=row["updated_at"] or "",
        )

    @staticmethod
    def _row_to_trade(row: sqlite3.Row) -> Trade:
        return Trade(
            id=row["id"],
            fund_id=row["fund_id"],
            trade_date=row["trade_date"],
            trade_type=row["trade_type"],
            strategy_type=row["strategy_type"] or "",
            nav=row["nav"],
            amount=row["amount"],
            shares=row["shares"],
            trigger_reason=row["trigger_reason"] or "",
            confirmed=row["confirmed"],
            created_at=row["created_at"] or "",
        )


# ==================== 建表 SQL ====================

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS fund (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    fund_type TEXT,
    main_ratio REAL DEFAULT 0.6,
    swing_ratio REAL DEFAULT 0.4,
    opportunity_line REAL,
    middle_line REAL,
    danger_line REAL,
    per_share_amount REAL DEFAULT 1250.0,
    total_shares_count INTEGER DEFAULT 10,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL REFERENCES fund(id),
    total_shares REAL DEFAULT 0.0,
    total_invested REAL DEFAULT 0.0,
    main_shares REAL DEFAULT 0.0,
    swing_shares REAL DEFAULT 0.0,
    anchor_nav REAL,
    highest_nav REAL,
    consecutive_buy INTEGER DEFAULT 0,
    consecutive_sell INTEGER DEFAULT 0,
    current_strategy TEXT DEFAULT 'none',
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(fund_id)
);

CREATE TABLE IF NOT EXISTS trade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL REFERENCES fund(id),
    trade_date TEXT NOT NULL,
    trade_type TEXT NOT NULL,
    strategy_type TEXT,
    nav REAL NOT NULL,
    amount REAL NOT NULL,
    shares REAL NOT NULL,
    trigger_reason TEXT,
    confirmed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
