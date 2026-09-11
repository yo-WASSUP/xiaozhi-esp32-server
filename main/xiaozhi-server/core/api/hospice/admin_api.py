"""Administrator account-management API."""
from __future__ import annotations

import sqlite3

from aiohttp import web

from core.api.hospice.auth import VALID_ROLES


class HospiceAdminHandler:
    def __init__(self, store):
        self.store = store

    def _users(self):
        users = []
        for row in self.store.list_users():
            if row["role"] == "admin":
                continue
            row["patient_ids"] = self.store.patient_ids(row["id"])
            users.append(row)
        return users

    def _audit(self, request: web.Request, action: str, target: str, detail: str = ""):
        admin = request["auth_user"]
        self.store.audit(
            admin.id,
            admin.username,
            admin.role,
            action,
            detail=f"{target}: {detail}".rstrip(": "),
            ip_address=request.remote or "",
        )

    async def list_users(self, request: web.Request):
        return web.json_response({"success": True, "users": self._users()})

    async def create_user(self, request: web.Request):
        try:
            data = await request.json()
            role = str(data.get("role") or "").strip().lower()
            if role not in VALID_ROLES:
                raise ValueError("账号角色无效")
            patient_ids = data.get("patient_ids") or []
            if not isinstance(patient_ids, list):
                raise ValueError("患者设备 ID 格式无效")
            if role == "patient" and not any(str(item).strip() for item in patient_ids):
                raise ValueError("患者账号必须填写患者设备 ID")
            user = self.store.create_user(
                str(data.get("username") or ""),
                str(data.get("password") or ""),
                str(data.get("display_name") or ""),
                role,
            )
            self.store.update_user(user.username, patient_ids=patient_ids)
            self._audit(request, "admin_create_user", user.username, role)
            return web.json_response({"success": True, "users": self._users()})
        except sqlite3.IntegrityError:
            return web.json_response({"success": False, "error": "用户名已存在"}, status=409)
        except (ValueError, TypeError) as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)

    async def update_user(self, request: web.Request):
        username = request.match_info["username"]
        try:
            data = await request.json()
            allowed = {"display_name", "password", "enabled", "patient_ids"}
            changes = {key: value for key, value in data.items() if key in allowed}
            if not changes:
                raise ValueError("没有需要保存的修改")
            if "enabled" in changes and not isinstance(changes["enabled"], bool):
                raise ValueError("账号状态格式无效")
            if "patient_ids" in changes and not isinstance(changes["patient_ids"], list):
                raise ValueError("患者设备 ID 格式无效")
            record = self.store.get_user_record(username)
            if record and record["role"] == "patient" and "patient_ids" in changes and not any(
                str(item).strip() for item in changes["patient_ids"]
            ):
                raise ValueError("患者账号必须保留患者设备 ID")
            self.store.update_user(username, **changes)
            self._audit(request, "admin_update_user", username, ",".join(sorted(changes)))
            return web.json_response({"success": True, "users": self._users()})
        except (ValueError, TypeError) as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)


def register_admin_routes(app: web.Application, store):
    handler = HospiceAdminHandler(store)
    app.add_routes(
        [
            web.get("/api/admin/users", handler.list_users),
            web.post("/api/admin/users", handler.create_user),
            web.patch("/api/admin/users/{username}", handler.update_user),
        ]
    )
