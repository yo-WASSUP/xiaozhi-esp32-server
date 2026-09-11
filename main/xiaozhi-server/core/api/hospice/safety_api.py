"""Clinician-only HTTP access to dignity safety tasks."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from aiohttp import web

from core.connection import ConnectionHandler
from core.dignity.runtime import SAFETY_ALERT_DIR, update_dignity_safety_task


_WRITE_LOCK = threading.Lock()
VALID_ACTIONS = {"acknowledge", "escalate", "release", "close"}


def _patient_key(patient_id: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", patient_id).strip("._")
    return key or "default_patient"


def _alert_path(patient_id: str) -> Path:
    return SAFETY_ALERT_DIR / f"{_patient_key(patient_id)}.jsonl"


def load_alerts(patient_id: str, limit: int = 50) -> list[dict]:
    path = _alert_path(patient_id)
    if not path.exists():
        return []
    latest: dict[str, dict] = {}
    with _WRITE_LOCK, path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                alert = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            alert_id = str(alert.get("alert_id") or "")
            if alert_id:
                latest[alert_id] = alert
    rows = sorted(latest.values(), key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 50), 200))]


def update_offline(patient_id: str, alert_id: str, action: str, operator: str, note: str) -> dict:
    alert = next((item for item in load_alerts(patient_id, 200) if item.get("alert_id") == alert_id), None)
    if not alert:
        raise ValueError("没有找到对应的安全预警任务")
    now = datetime.now().isoformat(timespec="seconds")
    task = alert.setdefault("task", {})
    alert["last_operator"] = operator
    alert["updated_at"] = now
    if note:
        alert["disposition_note"] = note
    if action == "acknowledge":
        task.update(status="acknowledged", acknowledged_at=now, acknowledged_by=operator)
    elif action == "escalate":
        alert.update(level="L3", requires_handoff=True, paused=True)
        task.update(
            status="escalated",
            priority="emergency",
            escalated_at=now,
            escalated_by=operator,
            recommended_action="立即人工接管并核实患者现实安全",
        )
    elif action == "release":
        task.update(status="released", released_at=now, released_by=operator)
        alert["resolved_at"] = now
    elif action == "close":
        task.update(status="closed", closed_at=now, closed_by=operator)
        alert["resolved_at"] = now
    path = _alert_path(patient_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK, path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(alert, ensure_ascii=False) + "\n")
    return alert


class HospiceSafetyHandler:
    def __init__(self, auth_store):
        self.auth_store = auth_store

    async def list(self, request: web.Request):
        patient_id = request.get("patient_id") or request.query.get("device_id", "")
        try:
            limit = int(request.query.get("limit", "50"))
            return web.json_response({"success": True, "alerts": load_alerts(patient_id, limit)})
        except (ValueError, OSError) as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)

    async def update(self, request: web.Request):
        try:
            data = await request.json()
            patient_id = request.get("patient_id") or str(data.get("device_id") or "")
            alert_id = str(data.get("alert_id") or "").strip()
            action = str(data.get("task_action") or "").strip().lower()
            note = str(data.get("note") or "").strip()[:500]
            user = request["auth_user"]
            operator = str(data.get("operator") or user.display_name or user.username).strip()[:60]
            if not alert_id or action not in VALID_ACTIONS:
                raise ValueError("安全预警处置参数无效")
            if not any(item.get("alert_id") == alert_id for item in load_alerts(patient_id, 200)):
                raise ValueError("没有找到对应的安全预警任务")

            with ConnectionHandler._active_connections_lock:
                connection = ConnectionHandler._active_connections.get(patient_id)
            if connection:
                await update_dignity_safety_task(
                    connection,
                    {
                        "patient_id": patient_id,
                        "alert_id": alert_id,
                        "task_action": action,
                        "operator": operator,
                        "note": note,
                    },
                )
                updated = next(
                    (item for item in load_alerts(patient_id, 200) if item.get("alert_id") == alert_id),
                    None,
                )
            else:
                updated = update_offline(patient_id, alert_id, action, operator, note)

            self.auth_store.audit(
                user.id,
                user.username,
                user.role,
                f"safety_{action}",
                patient_id=patient_id,
                detail=f"{alert_id}: {note}"[:500],
                ip_address=request.remote or "",
            )
            return web.json_response(
                {"success": True, "updated_alert": updated, "alerts": load_alerts(patient_id, 50)}
            )
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except OSError:
            return web.json_response({"success": False, "error": "安全预警记录写入失败"}, status=500)


def register_safety_routes(app: web.Application, auth_store):
    handler = HospiceSafetyHandler(auth_store)
    app.add_routes(
        [
            web.get("/api/hospice/safety-alerts", handler.list),
            web.patch("/api/hospice/safety-alerts/{alert_id}", handler.update),
        ]
    )
