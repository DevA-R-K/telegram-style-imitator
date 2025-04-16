import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import json

logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect("user_data.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS imitation_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        target TEXT,
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        style_data TEXT
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_target
    ON imitation_data (user_id, target)
    """)

    conn.commit()
    return conn, cursor

conn, cursor = init_db()

def save_messages(user_id: int, target: str, messages: List[str], style_data: Optional[Dict[str, Any]] = None):
    try:
        cursor.execute(
            "DELETE FROM imitation_data WHERE user_id = ? AND target = ?",
            (user_id, target)
        )

        style_data_json = json.dumps(style_data) if style_data else None

        for msg in messages:
            cursor.execute(
                """INSERT INTO imitation_data
                (user_id, target, message, timestamp, style_data)
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, target, msg, datetime.now(), style_data_json)
            )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных при сохранении сообщений: {e}")
        conn.rollback()

def get_messages(user_id: int, target: str, limit: int = 50) -> List[str]:
    try:
        cursor.execute(
            """SELECT message FROM imitation_data
            WHERE user_id = ? AND target = ?
            ORDER BY timestamp DESC LIMIT ?""",
            (user_id, target, limit)
        )
        return [msg[0] for msg in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных при получении сообщений: {e}")
        return []

def clear_data(user_id: int) -> bool:
    try:
        cursor.execute(
            "DELETE FROM imitation_data WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных при очистке данных: {e}")
        return False

def get_style_data_from_db(user_id: int, target: str) -> Optional[Dict[str, Any]]:
    try:
        cursor.execute(
            """SELECT style_data FROM imitation_data
            WHERE user_id = ? AND target = ?
            LIMIT 1""",
            (user_id, target)
        )
        result = cursor.fetchone()
        if result and result[0]:
            return json.loads(result[0])
        return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных при получении style_data: {e}")
        return None

def get_stats_data(user_id: int) -> Dict[str, List[str]]:
    stats_dict: Dict[str, List[str]] = {}
    try:
        cursor.execute("""
            SELECT target, message
            FROM imitation_data
            WHERE user_id = ?
            ORDER BY target, timestamp
        """, (user_id,))
        rows = cursor.fetchall()

        for target, message in rows:
            if target not in stats_dict:
                stats_dict[target] = []
            stats_dict[target].append(message)

        return stats_dict
    except sqlite3.Error as e:
        print(f"Database error in get_stats_data: {e}")
        logger.error(f"Database error in get_stats_data for user {user_id}: {e}")
        return {}
