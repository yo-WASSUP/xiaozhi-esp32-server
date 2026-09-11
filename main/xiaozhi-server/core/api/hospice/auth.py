"""Small-scale account authentication and patient authorization.

The implementation deliberately uses the existing SQLite database and opaque
refresh tokens. Access tokens are signed JWTs; passwords are stored as
PBKDF2-HMAC-SHA256 hashes and never as plaintext.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from urllib.parse import urlsplit
from dataclasses import dataclass
from typing import Optional

import jwt
from aiohttp import web


PASSWORD_ITERATIONS = 600_000
ACCESS_TOKEN_SECONDS = 12 * 60 * 60
REFRESH_TOKEN_SECONDS = 30 * 24 * 60 * 60
VALID_ROLES = {"patient", "family", "clinician"}


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    display_name: str
    role: str


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    if len(password or "") < 8:
        raise ValueError("密码至少需要 8 个字符")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        pad = lambda value: value + "=" * (-len(value) % 4)
        salt = base64.urlsafe_b64decode(pad(salt_text))
        expected = base64.urlsafe_b64decode(pad(digest_text))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations_text)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


class HospiceAuthStore:
    def __init__(self, db_path: str, secret_key: str, config: Optional[dict] = None):
        self.db_path = db_path
        self.secret_key = secret_key
        config = config or {}
        if config.get("enabled", False) is True and len(secret_key or "") < 32:
            raise ValueError("hospice.auth.secret_key 至少需要 32 个字符")
        self.access_token_seconds = int(config.get("access_token_seconds") or ACCESS_TOKEN_SECONDS)
        self.refresh_token_seconds = int(config.get("refresh_token_seconds") or REFRESH_TOKEN_SECONDS)
        self.max_failed_attempts = int(config.get("max_failed_attempts") or 5)
        self.lock_seconds = int(config.get("lock_seconds") or 600)
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()
        self._sync_config_admin(config)

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_user (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until INTEGER,
                    token_version INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS auth_user_patient_access (
                    user_id INTEGER NOT NULL,
                    patient_id TEXT NOT NULL,
                    permission TEXT NOT NULL DEFAULT 'standard',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, patient_id),
                    FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS auth_pairing_access (
                    user_id INTEGER NOT NULL,
                    family_id TEXT NOT NULL,
                    patient_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, family_id),
                    FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS auth_refresh_token (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS auth_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    role TEXT,
                    action TEXT NOT NULL,
                    patient_id TEXT,
                    detail TEXT,
                    ip_address TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_auth_access_patient
                    ON auth_user_patient_access(patient_id);
                CREATE INDEX IF NOT EXISTS idx_auth_refresh_user
                    ON auth_refresh_token(user_id);
                """
            )

    def _sync_config_admin(self, config: dict):
        username = str(config.get("admin_username") or "").strip()
        password = str(config.get("admin_password") or "")
        if config.get("enabled", False) is not True:
            return
        if not username or len(password) < 8:
            raise ValueError("启用登录时必须配置 admin_username 和至少 8 个字符的 admin_password")
        record = self.get_user_record(username)
        if record and record["role"] != "admin":
            raise ValueError("admin_username 与现有普通账号重名")
        with self.connect() as conn:
            conn.execute(
                "UPDATE auth_user SET enabled=0,token_version=token_version+1 "
                "WHERE role='admin' AND username<>? COLLATE NOCASE AND enabled=1",
                (username,),
            )
            if record:
                password_changed = not verify_password(password, record["password_hash"])
                conn.execute(
                    "UPDATE auth_user SET password_hash=?,display_name='系统管理员',enabled=1,"
                    "failed_attempts=0,locked_until=NULL,token_version=token_version+?,"
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (
                        hash_password(password) if password_changed else record["password_hash"],
                        1 if password_changed else 0,
                        record["id"],
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO auth_user(username,password_hash,display_name,role) VALUES(?,?,?,'admin')",
                    (username, hash_password(password), "系统管理员"),
                )

    def create_user(self, username: str, password: str, display_name: str, role: str) -> AuthUser:
        username = (username or "").strip()
        display_name = (display_name or username).strip()
        role = (role or "").strip().lower()
        if not username or len(username) > 80:
            raise ValueError("用户名长度无效")
        if role not in VALID_ROLES:
            raise ValueError("角色必须是 patient、family 或 clinician")
        password_hash = hash_password(password)
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO auth_user(username,password_hash,display_name,role) VALUES(?,?,?,?)",
                (username, password_hash, display_name, role),
            )
            user_id = cursor.lastrowid
        return AuthUser(user_id, username, display_name, role)

    def get_user(self, user_id: int) -> Optional[AuthUser]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id,username,display_name,role FROM auth_user WHERE id=? AND enabled=1",
                (user_id,),
            ).fetchone()
        return AuthUser(**dict(row)) if row else None

    def get_user_record(self, username: str):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM auth_user WHERE username=? COLLATE NOCASE", ((username or "").strip(),)
            ).fetchone()

    def list_users(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id,username,display_name,role,enabled,locked_until,created_at FROM auth_user ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_user(
        self,
        username: str,
        *,
        display_name: Optional[str] = None,
        password: Optional[str] = None,
        enabled: Optional[bool] = None,
        patient_ids: Optional[list[str]] = None,
    ):
        record = self.get_user_record(username)
        if not record or record["role"] == "admin":
            raise ValueError("账号不存在")
        if display_name is not None and not str(display_name).strip():
            raise ValueError("姓名不能为空")
        normalized_ids = None
        if patient_ids is not None:
            normalized_ids = list(dict.fromkeys(str(item).strip() for item in patient_ids if str(item).strip()))
        password_hash = hash_password(password) if password is not None else None
        with self.connect() as conn:
            if display_name is not None:
                conn.execute(
                    "UPDATE auth_user SET display_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (str(display_name).strip(), record["id"]),
                )
            if password_hash is not None:
                conn.execute(
                    "UPDATE auth_user SET password_hash=?,failed_attempts=0,locked_until=NULL,"
                    "token_version=token_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (password_hash, record["id"]),
                )
            if enabled is not None:
                conn.execute(
                    "UPDATE auth_user SET enabled=?,token_version=token_version+1,"
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (1 if enabled else 0, record["id"]),
                )
            if normalized_ids is not None:
                conn.execute("DELETE FROM auth_user_patient_access WHERE user_id=?", (record["id"],))
                conn.executemany(
                    "INSERT INTO auth_user_patient_access(user_id,patient_id) VALUES(?,?)",
                    ((record["id"], patient_id) for patient_id in normalized_ids),
                )
            if password_hash is not None or enabled is not None:
                conn.execute(
                    "UPDATE auth_refresh_token SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                    (int(time.time()), record["id"]),
                )

    def patient_ids(self, user_id: int) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT patient_id, MIN(created_at) AS granted_at FROM ("
                "SELECT patient_id,created_at FROM auth_user_patient_access WHERE user_id=? UNION ALL "
                "SELECT patient_id,created_at FROM auth_pairing_access WHERE user_id=?"
                ") GROUP BY patient_id ORDER BY granted_at",
                (user_id, user_id),
            ).fetchall()
        return [row["patient_id"] for row in rows]

    def can_access_patient(self, user: AuthUser, patient_id: str) -> bool:
        if not patient_id:
            return False
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM auth_user_patient_access WHERE user_id=? AND patient_id=? "
                "UNION ALL SELECT 1 FROM auth_pairing_access WHERE user_id=? AND patient_id=? LIMIT 1",
                (user.id, patient_id, user.id, patient_id),
            ).fetchone()
        return bool(row)

    def add_pairing_access(self, user: AuthUser, family_id: str, patient_id: str):
        if user.role != "family" or not family_id or not patient_id:
            raise ValueError("配对授权参数无效")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO auth_pairing_access(user_id,family_id,patient_id) VALUES(?,?,?) "
                "ON CONFLICT(user_id,family_id) DO UPDATE SET patient_id=excluded.patient_id",
                (user.id, family_id, patient_id),
            )

    def remove_pairing_access(self, family_id: str, patient_id: str):
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM auth_pairing_access WHERE family_id=? AND patient_id=?",
                (family_id, patient_id),
            )

    def owns_pairing(self, user: AuthUser, family_id: str, patient_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM auth_pairing_access WHERE user_id=? AND family_id=? AND patient_id=?",
                (user.id, family_id, patient_id),
            ).fetchone()
        return bool(row)

    def authenticate(self, username: str, password: str, ip_address: str = "") -> Optional[AuthUser]:
        record = self.get_user_record(username)
        now = int(time.time())
        if not record or not record["enabled"]:
            self.audit(None, username, "", "login_failed", detail="unknown_or_disabled", ip_address=ip_address)
            return None
        if record["locked_until"] and int(record["locked_until"]) > now:
            self.audit(None, record["username"], record["role"], "login_failed", detail="locked", ip_address=ip_address)
            raise AuthError("账号暂时锁定，请稍后再试")
        if not verify_password(password or "", record["password_hash"]):
            failed = int(record["failed_attempts"] or 0) + 1
            locked_until = now + self.lock_seconds if failed >= self.max_failed_attempts else None
            with self.connect() as conn:
                conn.execute(
                    "UPDATE auth_user SET failed_attempts=?,locked_until=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (0 if locked_until else failed, locked_until, record["id"]),
                )
            self.audit(record["id"], record["username"], record["role"], "login_failed", detail="bad_password", ip_address=ip_address)
            return None
        with self.connect() as conn:
            conn.execute(
                "UPDATE auth_user SET failed_attempts=0,locked_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (record["id"],),
            )
        user = AuthUser(record["id"], record["username"], record["display_name"], record["role"])
        self.audit(user.id, user.username, user.role, "login_success", ip_address=ip_address)
        return user

    def issue_tokens(self, user: AuthUser) -> dict:
        record = self.get_user_record(user.username)
        now = int(time.time())
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "type": "access",
            "ver": int(record["token_version"]),
            "iat": now,
            "exp": now + self.access_token_seconds,
            "jti": uuid.uuid4().hex,
        }
        access_token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        refresh_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO auth_refresh_token(token_hash,user_id,expires_at) VALUES(?,?,?)",
                (token_hash, user.id, now + self.refresh_token_seconds),
            )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self.access_token_seconds,
        }

    def verify_access_token(self, token: str) -> AuthUser:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            if payload.get("type") != "access":
                raise AuthError("令牌类型无效")
            user_id = int(payload["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AuthError("登录已失效") from exc
        record = self.get_user_record(str(payload.get("username") or ""))
        if not record or not record["enabled"] or record["id"] != user_id:
            raise AuthError("账号不可用")
        if int(record["token_version"]) != int(payload.get("ver") or 0):
            raise AuthError("登录已失效")
        return AuthUser(record["id"], record["username"], record["display_name"], record["role"])

    def refresh(self, refresh_token: str) -> tuple[AuthUser, dict]:
        token_hash = hashlib.sha256((refresh_token or "").encode("utf-8")).hexdigest()
        now = int(time.time())
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM auth_refresh_token WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
                (token_hash, now),
            ).fetchone()
            if not row:
                raise AuthError("刷新令牌无效")
            conn.execute(
                "UPDATE auth_refresh_token SET revoked_at=? WHERE token_hash=?", (now, token_hash)
            )
        user = self.get_user(int(row["user_id"]))
        if not user:
            raise AuthError("账号不可用")
        return user, self.issue_tokens(user)

    def revoke_refresh(self, refresh_token: str):
        token_hash = hashlib.sha256((refresh_token or "").encode("utf-8")).hexdigest()
        with self.connect() as conn:
            conn.execute(
                "UPDATE auth_refresh_token SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (int(time.time()), token_hash),
            )

    def audit(
        self,
        user_id: Optional[int],
        username: str,
        role: str,
        action: str,
        *,
        patient_id: str = "",
        detail: str = "",
        ip_address: str = "",
    ):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO auth_audit_log(user_id,username,role,action,patient_id,detail,ip_address) "
                "VALUES(?,?,?,?,?,?,?)",
                (user_id, username, role, action, patient_id or None, detail or None, ip_address or None),
            )

    def user_payload(self, user: AuthUser) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "patient_ids": self.patient_ids(user.id),
        }


def _session_role(request: web.Request) -> str:
    """Select a session slot; authorization still comes from the signed token."""
    role = request.headers.get("X-Hospice-Role", "")
    if not role:
        role = urlsplit(request.headers.get("Referer", "")).path.strip("/").split("/", 1)[0]
    if not role and request.path in ("/api/hospice/call/ws", "/api/hospice/wakeword/ws"):
        role = request.query.get("role", "")
    return role if role in VALID_ROLES | {"admin"} else ""


def _cookie_name(request: web.Request, kind: str) -> str:
    role = _session_role(request)
    return f"hospice_{kind}_{role}" if role else f"hospice_{kind}"


def _bearer_token(request: web.Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (
        request.cookies.get(_cookie_name(request, "access"))
        or ""
    ).strip()


async def _request_patient_id(request: web.Request) -> str:
    for key in ("device_id", "patient_id"):
        value = (request.query.get(key) or request.headers.get(key.replace("_", "-"), "")).strip()
        if value:
            return value
    if request.can_read_body and request.content_type == "application/json":
        try:
            data = await request.json()
        except Exception:
            data = {}
        for key in ("device_id", "patient_id"):
            value = str(data.get(key) or "").strip()
            if value:
                return value
    for key in ("device_id", "patient_id"):
        value = str(request.match_info.get(key) or "").strip()
        if value:
            return value
    return ""


def build_auth_middleware(store: HospiceAuthStore, config: Optional[dict] = None):
    config = config or {}
    enabled = config.get("enabled", False) is True
    public_paths = {
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/status",
        "/api/hospice/config",
    }
    patient_only_prefixes = (
        "/api/hospice/voice-clone/",
        "/api/hospice/pairing/code",
        "/api/hospice/pairing/families",
        "/api/hospice/tts/",
        "/api/hospice/wakeword/",
    )
    family_denied_prefixes = (
        "/api/hospice/contacts",
        "/api/hospice/thread/",
        "/api/hospice/interview/",
        "/api/hospice/legacy-card/render",
        "/api/hospice/family-letter/render",
    )
    clinician_denied_prefixes = (
        "/api/hospice/message",
        "/api/hospice/messages",
        "/api/hospice/pairing/",
        "/api/hospice/call/",
        "/api/hospice/tts/",
        "/api/hospice/voice-clone/",
        "/api/hospice/wakeword/",
        "/api/hospice/upload",
    )
    patient_context_prefixes = (
        "/api/hospice/summary/",
        "/api/hospice/emotion/",
        "/api/hospice/message",
        "/api/hospice/messages",
        "/api/hospice/contacts",
        "/api/hospice/thread/",
        "/api/hospice/tts/",
        "/api/hospice/voice-clone/",
        "/api/hospice/pairing/code",
        "/api/hospice/pairing/families",
        "/api/hospice/pairing/bindings",
        "/api/hospice/call/",
        "/api/hospice/wakeword/",
        "/api/hospice/upload",
        "/api/hospice/conversations/",
        "/api/hospice/interview/",
        "/api/hospice/legacy-card/",
        "/api/hospice/family-letter/",
        "/api/hospice/video/",
        "/api/hospice/safety-alerts",
    )

    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        path = request.path
        protected = (
            path.startswith("/api/hospice/")
            or path.startswith("/api/auth/")
            or path.startswith("/api/admin/")
            or path.startswith("/hospice-media/")
        )
        if not enabled or request.method == "OPTIONS" or path in public_paths or not protected:
            return await handler(request)
        token = _bearer_token(request)
        if not token:
            return web.json_response({"success": False, "error": "请先登录"}, status=401)
        try:
            user = store.verify_access_token(token)
        except AuthError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=401)
        request["auth_user"] = user
        request["auth_store"] = store

        if path.startswith("/api/admin/"):
            if user.role != "admin":
                return web.json_response({"success": False, "error": "仅管理员可以管理账号"}, status=403)
            return await handler(request)

        if user.role == "admin" and path.startswith("/api/hospice/"):
            return web.json_response({"success": False, "error": "管理员账号仅用于账号管理"}, status=403)

        if path.startswith("/api/hospice/safety-alerts") and user.role != "clinician":
            return web.json_response({"success": False, "error": "安全预警处置仅限医护账号"}, status=403)

        if path == "/api/hospice/pairing/bind":
            if user.role != "family":
                return web.json_response({"success": False, "error": "只有家属账号可以绑定患者"}, status=403)
            response = await handler(request)
            if response.status < 400 and response.body:
                try:
                    import json

                    binding = json.loads(response.body).get("binding") or {}
                    store.add_pairing_access(
                        user,
                        str(binding.get("family_id") or ""),
                        str(binding.get("device_id") or ""),
                    )
                    store.audit(
                        user.id,
                        user.username,
                        user.role,
                        "pair_patient",
                        patient_id=str(binding.get("device_id") or ""),
                        detail=str(binding.get("family_id") or ""),
                        ip_address=request.remote or "",
                    )
                except (ValueError, TypeError):
                    pass
            return response

        if path.startswith(patient_only_prefixes) and user.role not in {"patient", "clinician"}:
            return web.json_response({"success": False, "error": "当前账号没有此操作权限"}, status=403)

        if user.role == "family" and path.startswith(family_denied_prefixes):
            return web.json_response({"success": False, "error": "家属账号没有此操作权限"}, status=403)

        if user.role == "clinician" and path.startswith(clinician_denied_prefixes):
            return web.json_response({"success": False, "error": "医护账号没有此操作权限"}, status=403)

        if path == "/api/hospice/call/ws":
            requested_role = request.query.get("role", "")
            if requested_role != user.role or user.role not in {"patient", "family"}:
                return web.Response(status=403, text="role does not match login")

        patient_id = await _request_patient_id(request)
        if path.startswith(patient_context_prefixes) and not patient_id:
            return web.json_response({"success": False, "error": "请求缺少患者标识"}, status=400)
        if patient_id and not store.can_access_patient(user, patient_id):
            return web.json_response({"success": False, "error": "没有该患者的访问权限"}, status=403)
        if path == "/api/hospice/pairing/bindings" and request.method == "DELETE" and user.role == "family":
            family_id = str(request.query.get("family_id") or "").strip()
            if not store.owns_pairing(user, family_id, patient_id):
                return web.json_response({"success": False, "error": "只能解除当前家属账号的绑定"}, status=403)
        request["patient_id"] = patient_id
        response = await handler(request)
        if path == "/api/hospice/pairing/bindings" and request.method == "DELETE" and response.status < 400:
            try:
                import json

                binding = json.loads(response.body).get("binding") or {}
                store.remove_pairing_access(
                    str(binding.get("family_id") or ""),
                    str(binding.get("device_id") or patient_id),
                )
            except (ValueError, TypeError):
                pass
        return response

    return auth_middleware


class HospiceAuthHandler:
    def __init__(self, store: HospiceAuthStore, enabled: bool):
        self.store = store
        self.enabled = enabled

    @staticmethod
    def _ip(request: web.Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        return forwarded or (request.remote or "")

    async def login(self, request: web.Request):
        try:
            data = await request.json()
            user = self.store.authenticate(data.get("username", ""), data.get("password", ""), self._ip(request))
            if not user:
                return web.json_response({"success": False, "error": "账号或密码错误"}, status=401)
            role = _session_role(request)
            if role and role != user.role:
                return web.json_response({"success": False, "error": "请使用当前端对应的账号登录"}, status=403)
            tokens = self.store.issue_tokens(user)
            response = web.json_response({"success": True, "user": self.store.user_payload(user)})
            self._set_cookies(response, request, tokens)
            return response
        except AuthError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=423)
        except Exception:
            return web.json_response({"success": False, "error": "登录请求无效"}, status=400)

    async def refresh(self, request: web.Request):
        try:
            try:
                data = await request.json()
            except Exception:
                data = {}
            refresh_token = request.cookies.get(_cookie_name(request, "refresh")) or data.get("refresh_token") or ""
            user, tokens = self.store.refresh(str(refresh_token))
            response = web.json_response({"success": True, "user": self.store.user_payload(user)})
            self._set_cookies(response, request, tokens)
            return response
        except AuthError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=401)

    async def logout(self, request: web.Request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        refresh_token = request.cookies.get(_cookie_name(request, "refresh")) or data.get("refresh_token") or ""
        self.store.revoke_refresh(str(refresh_token))
        response = web.json_response({"success": True})
        response.del_cookie(_cookie_name(request, "access"), path="/")
        response.del_cookie(_cookie_name(request, "refresh"), path="/api/auth")
        return response

    async def me(self, request: web.Request):
        user = request.get("auth_user")
        if not user:
            return web.json_response({"success": False, "error": "请先登录"}, status=401)
        return web.json_response({"success": True, "user": self.store.user_payload(user)})

    async def status(self, request: web.Request):
        return web.json_response({"success": True, "enabled": self.enabled})

    def _set_cookies(self, response: web.Response, request: web.Request, tokens: dict):
        secure = request.secure
        response.set_cookie(
            _cookie_name(request, "access"),
            tokens["access_token"],
            max_age=self.store.access_token_seconds,
            httponly=True,
            secure=secure,
            samesite="Lax",
            path="/",
        )
        response.set_cookie(
            _cookie_name(request, "refresh"),
            tokens["refresh_token"],
            max_age=self.store.refresh_token_seconds,
            httponly=True,
            secure=secure,
            samesite="Strict",
            path="/api/auth",
        )


def register_auth_routes(app: web.Application, store: HospiceAuthStore, config: Optional[dict] = None):
    handler = HospiceAuthHandler(store, (config or {}).get("enabled", False) is True)
    app.add_routes(
        [
            web.post("/api/auth/login", handler.login),
            web.post("/api/auth/refresh", handler.refresh),
            web.post("/api/auth/logout", handler.logout),
            web.get("/api/auth/me", handler.me),
            web.get("/api/auth/status", handler.status),
        ]
    )
