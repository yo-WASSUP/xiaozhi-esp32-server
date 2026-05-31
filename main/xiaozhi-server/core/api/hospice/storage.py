"""
会话日志模块 - 将对话和情感数据记录到 SQLite
"""
import sqlite3
import json
import os
import time
import uuid
import random
from datetime import datetime, date
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class SessionLogger:
    """安宁疗护会话日志记录器"""

    def __init__(self, db_path: str = "data/hospice_sessions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        logger.bind(tag=TAG).info(f"会话日志初始化完成: {db_path}")

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                session_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT,
                content TEXT,
                emotion_mood TEXT,
                emotion_intensity REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                date DATE,
                summary TEXT,
                mood_trend TEXT,
                conversation_count INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS family_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                sender_name TEXT,
                message_type TEXT,
                content TEXT,
                file_path TEXT,
                played INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 兼容旧库：补列
        cursor.execute("PRAGMA table_info(family_message)")
        cols = {row[1] for row in cursor.fetchall()}
        if "sender_role" not in cols:
            cursor.execute("ALTER TABLE family_message ADD COLUMN sender_role TEXT DEFAULT 'family'")
        if "duration_ms" not in cols:
            cursor.execute("ALTER TABLE family_message ADD COLUMN duration_ms INTEGER")
        if "read_at" not in cols:
            cursor.execute("ALTER TABLE family_message ADD COLUMN read_at DATETIME")
        if "contact_name" not in cols:
            cursor.execute("ALTER TABLE family_message ADD COLUMN contact_name TEXT")
            # 回填：家属发送的消息以 sender_name 作为会话键
            cursor.execute(
                "UPDATE family_message SET contact_name = sender_name "
                "WHERE contact_name IS NULL AND sender_role = 'family'"
            )
        if "family_id" not in cols:
            cursor.execute("ALTER TABLE family_message ADD COLUMN family_id TEXT")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pairing_code (
                code TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                used_at INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS family_binding (
                family_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                family_name TEXT NOT NULL,
                relationship TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                revoked_at DATETIME
            )
        """)

        conn.commit()
        conn.close()

    def log_conversation(self, device_id: str, session_id: str, role: str,
                         content: str, emotion_mood: str = None,
                         emotion_intensity: float = None):
        """记录一条对话"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO conversation_log 
                   (device_id, session_id, role, content, emotion_mood, emotion_intensity)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (device_id, session_id, role, content, emotion_mood, emotion_intensity)
            )
            conn.commit()
            conn.close()
            logger.bind(tag=TAG).debug(f"对话已记录: [{role}] {content[:30]}...")
        except Exception as e:
            logger.bind(tag=TAG).error(f"记录对话失败: {e}")

    def get_today_conversations(self, device_id: str) -> list:
        """获取今日对话记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            today = date.today().isoformat()
            cursor.execute(
                """SELECT * FROM conversation_log 
                   WHERE device_id = ? AND DATE(timestamp) = ?
                   ORDER BY timestamp ASC""",
                (device_id, today)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取今日对话失败: {e}")
            return []

    def get_conversations_by_date(self, device_id: str, day: str) -> list:
        """Get conversation records for one yyyy-mm-dd date."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM conversation_log
                   WHERE device_id = ? AND DATE(timestamp) = ?
                   ORDER BY timestamp ASC""",
                (device_id, day)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取指定日期对话失败: {e}")
            return []

    def get_latest_conversation_date(self, device_id: str):
        """Get the latest date that has conversation records for a device."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """SELECT DATE(timestamp) FROM conversation_log
                   WHERE device_id = ?
                   ORDER BY timestamp DESC
                   LIMIT 1""",
                (device_id,)
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取最近对话日期失败: {e}")
            return None

    def get_today_emotions(self, device_id: str) -> list:
        """获取今日情绪变化"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            today = date.today().isoformat()
            cursor.execute(
                """SELECT timestamp, emotion_mood, emotion_intensity 
                   FROM conversation_log 
                   WHERE device_id = ? AND DATE(timestamp) = ? 
                   AND emotion_mood IS NOT NULL
                   ORDER BY timestamp ASC""",
                (device_id, today)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取今日情绪失败: {e}")
            return []

    def get_emotions_by_date(self, device_id: str, day: str) -> list:
        """Get emotion records for one yyyy-mm-dd date."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT timestamp, emotion_mood, emotion_intensity
                   FROM conversation_log
                   WHERE device_id = ? AND DATE(timestamp) = ?
                   AND emotion_mood IS NOT NULL
                   ORDER BY timestamp ASC""",
                (device_id, day)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取指定日期情绪失败: {e}")
            return []

    def get_emotion_trend(self, device_id: str, days: int = 7) -> list:
        """获取近N天情绪趋势"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT DATE(timestamp) as date, 
                   emotion_mood, 
                   AVG(emotion_intensity) as avg_intensity,
                   COUNT(*) as count
                   FROM conversation_log 
                   WHERE device_id = ? 
                   AND emotion_mood IS NOT NULL
                   AND timestamp >= datetime('now', ?)
                   GROUP BY DATE(timestamp), emotion_mood
                   ORDER BY date ASC""",
                (device_id, f'-{days} days')
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取情绪趋势失败: {e}")
            return []

    def save_daily_summary(self, device_id: str, summary: str, mood_trend: str,
                           conversation_count: int):
        """保存每日摘要"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            today = date.today().isoformat()
            # 先删除今日已有摘要（覆盖更新）
            cursor.execute(
                "DELETE FROM daily_summary WHERE device_id = ? AND date = ?",
                (device_id, today)
            )
            cursor.execute(
                """INSERT INTO daily_summary 
                   (device_id, date, summary, mood_trend, conversation_count)
                   VALUES (?, ?, ?, ?, ?)""",
                (device_id, today, summary, mood_trend, conversation_count)
            )
            conn.commit()
            conn.close()
            logger.bind(tag=TAG).info(f"每日摘要已保存: {device_id}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"保存每日摘要失败: {e}")

    def get_summary_today(self, device_id: str) -> dict:
        """获取今日摘要"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            today = date.today().isoformat()
            cursor.execute(
                "SELECT * FROM daily_summary WHERE device_id = ? AND date = ?",
                (device_id, today)
            )
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取今日摘要失败: {e}")
            return None

    def get_summary_history(self, device_id: str, limit: int = 30) -> list:
        """获取历史摘要"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM daily_summary 
                   WHERE device_id = ? 
                   ORDER BY date DESC LIMIT ?""",
                (device_id, limit)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取历史摘要失败: {e}")
            return []

    def save_family_message(self, device_id: str, sender_name: str,
                            message_type: str, content: str = None,
                            file_path: str = None,
                            sender_role: str = "family",
                            duration_ms: int = None,
                            contact_name: str = None,
                            family_id: str = None):
        """保存一条消息（家属发给患者 或 患者发给家属）

        contact_name 是会话键：这条消息属于"患者 <-> 哪位家属"这条会话线。
        - 家属发送时：若未指定，默认取 sender_name（该家属自己的名字）。
        - 患者发送时：必须指定（回复的是哪位家属）。
        """
        if family_id and not contact_name:
            binding = self.get_family_binding(device_id, family_id)
            if binding:
                contact_name = binding.get("family_name")
        if contact_name is None and sender_role == "family":
            contact_name = sender_name
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO family_message
                   (device_id, sender_name, sender_role, message_type, content, file_path, duration_ms, contact_name, family_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (device_id, sender_name, sender_role, message_type, content, file_path, duration_ms, contact_name, family_id)
            )
            conn.commit()
            msg_id = cursor.lastrowid
            # 读回完整行用于广播
            cursor.execute("SELECT * FROM family_message WHERE id=?", (msg_id,))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM family_message WHERE id=?", (msg_id,))
            row = cursor.fetchone()
            conn.close()
            logger.bind(tag=TAG).info(f"消息已保存: {sender_role}/{sender_name} -> {device_id} (id={msg_id})")
            return dict(row) if row else {"id": msg_id}
        except Exception as e:
            logger.bind(tag=TAG).error(f"保存消息失败: {e}")
            return None

    def get_family_messages(self, device_id: str, limit: int = 50,
                            sender_role: str = None,
                            contact_name: str = None,
                            family_id: str = None) -> list:
        """获取消息列表；可按 sender_role 和/或 contact_name 过滤"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            clauses = ["device_id = ?"]
            params: list = [device_id]
            if sender_role:
                clauses.append("sender_role = ?")
                params.append(sender_role)
            if contact_name:
                clauses.append("contact_name = ?")
                params.append(contact_name)
            if family_id:
                clauses.append("family_id = ?")
                params.append(family_id)
            sql = (
                "SELECT * FROM family_message WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC LIMIT ?"
            )
            params.append(limit)
            cursor.execute(sql, tuple(params))
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取消息失败: {e}")
            return []

    def get_contacts(self, device_id: str) -> list:
        """获取联系人列表（按 contact_name 聚合），包含最后一条消息与未读数。

        返回：
        [
          {
            contact_name, last_type, last_content, last_sender_role,
            last_time, unread
          }, ...
        ]
        按 last_time 倒序。
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # 每个 contact 取 id 最大的那条作为"最后一条"
            cursor.execute(
                """
                SELECT fm.contact_name,
                       fm.family_id,
                       fm.message_type  AS last_type,
                       fm.content       AS last_content,
                       fm.sender_role   AS last_sender_role,
                       fm.sender_name   AS last_sender_name,
                       fm.created_at    AS last_time,
                       (SELECT COUNT(*) FROM family_message
                        WHERE device_id = ? AND IFNULL(family_id, contact_name) = IFNULL(fm.family_id, fm.contact_name)
                          AND sender_role = 'family' AND IFNULL(played,0) = 0
                       ) AS unread
                FROM family_message fm
                WHERE fm.device_id = ? AND fm.contact_name IS NOT NULL
                  AND fm.id = (
                      SELECT MAX(id) FROM family_message
                      WHERE device_id = fm.device_id
                        AND IFNULL(family_id, contact_name) = IFNULL(fm.family_id, fm.contact_name)
                  )
                ORDER BY fm.created_at DESC
                """,
                (device_id, device_id),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取联系人失败: {e}")
            return []

    def mark_thread_read(self, device_id: str, contact_name: str = None, family_id: str = None) -> int:
        """把某个联系人会话中所有家属消息标记为已读，返回更新条数"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if family_id:
                cursor.execute(
                    """UPDATE family_message
                       SET played = 1, read_at = CURRENT_TIMESTAMP
                       WHERE device_id = ? AND family_id = ?
                         AND sender_role = 'family' AND IFNULL(played,0) = 0""",
                    (device_id, family_id),
                )
            else:
                cursor.execute(
                    """UPDATE family_message
                       SET played = 1, read_at = CURRENT_TIMESTAMP
                       WHERE device_id = ? AND contact_name = ?
                         AND sender_role = 'family' AND IFNULL(played,0) = 0""",
                    (device_id, contact_name),
                )
            conn.commit()
            changed = cursor.rowcount
            conn.close()
            return changed
        except Exception as e:
            logger.bind(tag=TAG).error(f"标记会话已读失败: {e}")
            return 0

    def mark_message_read(self, msg_id: int) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE family_message SET played=1, read_at=CURRENT_TIMESTAMP WHERE id=?",
                (msg_id,)
            )
            conn.commit()
            changed = cursor.rowcount
            conn.close()
            return changed > 0
        except Exception as e:
            logger.bind(tag=TAG).error(f"标记已读失败: {e}")
            return False

    def create_pairing_code(self, device_id: str, ttl_seconds: int = 600) -> dict:
        code = f"{random.randint(0, 999999):06d}"
        expires_at = int(time.time()) + ttl_seconds
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pairing_code WHERE device_id = ? OR expires_at < ?", (device_id, int(time.time())))
            cursor.execute(
                "INSERT INTO pairing_code (code, device_id, expires_at) VALUES (?, ?, ?)",
                (code, device_id, expires_at),
            )
            conn.commit()
            conn.close()
            return {"code": code, "device_id": device_id, "expires_at": expires_at}
        except Exception as e:
            logger.bind(tag=TAG).error(f"创建配对码失败: {e}")
            return {}

    def bind_family(self, code: str, family_name: str, relationship: str = None) -> dict:
        now = int(time.time())
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pairing_code WHERE code = ? AND used_at IS NULL AND expires_at >= ?",
                (code, now),
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return {}
            family_id = uuid.uuid4().hex
            device_id = row["device_id"]
            cursor.execute(
                """INSERT INTO family_binding
                   (family_id, device_id, family_name, relationship)
                   VALUES (?, ?, ?, ?)""",
                (family_id, device_id, family_name, relationship),
            )
            cursor.execute("UPDATE pairing_code SET used_at = ? WHERE code = ?", (now, code))
            conn.commit()
            cursor.execute("SELECT * FROM family_binding WHERE family_id = ?", (family_id,))
            binding = dict(cursor.fetchone())
            conn.close()
            return binding
        except Exception as e:
            logger.bind(tag=TAG).error(f"绑定家属失败: {e}")
            return {}

    def get_family_binding(self, device_id: str, family_id: str) -> dict:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM family_binding WHERE device_id = ? AND family_id = ? AND revoked_at IS NULL",
                (device_id, family_id),
            )
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取家属绑定失败: {e}")
            return {}

    def get_family_bindings(self, device_id: str) -> list:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT family_id, family_name, relationship, created_at
                   FROM family_binding
                   WHERE device_id = ? AND revoked_at IS NULL
                   ORDER BY created_at DESC""",
                (device_id,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.bind(tag=TAG).error(f"获取家属列表失败: {e}")
            return []


# 全局单例
_session_logger = None


def get_session_logger(config: dict = None) -> SessionLogger:
    """获取会话日志单例"""
    global _session_logger
    if _session_logger is None:
        db_path = "data/hospice_sessions.db"
        if config:
            hospice_config = config.get("hospice", {})
            db_path = hospice_config.get("db_path", db_path)
        _session_logger = SessionLogger(db_path)
    return _session_logger
