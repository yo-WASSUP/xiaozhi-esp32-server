import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.dignity.runtime import (
    _create_safety_alert,
    _load_safety_alerts,
    handle_dignity_turn_if_active,
    list_dignity_safety_alerts,
    resume_dignity_mode,
    update_dignity_safety_task,
)
from core.dignity.safety import assess_safety_risk


class DignitySafetyRuleTests(unittest.TestCase):
    def test_negated_self_harm_statement_does_not_trigger(self):
        result = assess_safety_risk("我没有想过自杀，现在只是有点累。")

        self.assertEqual(result["level"], "L0")
        self.assertFalse(result["requires_alert"])

    def test_passive_death_wish_is_level_one(self):
        result = assess_safety_risk("我觉得活着没意思，自己是家里的负担。")

        self.assertEqual(result["level"], "L1")
        self.assertFalse(result["requires_pause"])

    def test_active_self_harm_thought_is_level_two(self):
        result = assess_safety_risk("我最近想自杀。")

        self.assertEqual(result["level"], "L2")
        self.assertTrue(result["requires_pause"])
        self.assertFalse(result["requires_handoff"])

    def test_immediate_intent_is_level_three(self):
        result = assess_safety_risk("我现在就想死，药已经准备好了。")

        self.assertEqual(result["level"], "L3")
        self.assertTrue(result["requires_handoff"])

    def test_unverifiable_model_evidence_cannot_force_emergency_pause(self):
        result = assess_safety_risk(
            "我今天只是有点难过。",
            {
                "level": "L3",
                "category": "self_harm",
                "evidence": "我已经准备好了药",
                "reason": "存在近期行为",
            },
        )

        self.assertEqual(result["level"], "L1")
        self.assertFalse(result["requires_pause"])


def build_connection():
    logger = Mock()
    logger.bind.return_value = logger
    return SimpleNamespace(
        dignity_active=True,
        dignity_state=None,
        dignity_debug_state=None,
        dignity_patient_id="patient-1",
        dignity_decision_model=None,
        dignity_paused=False,
        dignity_pause_reason="",
        dignity_paused_at="",
        dignity_silence_prompt_count=0,
        dignity_safety_alert=None,
        websocket=AsyncMock(),
        session_id="session-1",
        config={},
        executor=None,
        client_abort=False,
        logger=logger,
    )


class DignitySafetyRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_level_three_alert_is_saved_pushed_and_pauses_interview(self):
        conn = build_connection()
        state = {
            "strategy": "continue_deeper",
            "reply": "请继续说。",
            "current_stage": "life_review",
            "turn_count": 1,
            "followup_count": 1,
            "emotion_state": {"mood": "sad", "engagement": "low"},
            "dignity_memory": {},
            "transcript": [
                {
                    "patient": "我现在就想死。",
                    "assistant": "请继续说。",
                    "strategy": "continue_deeper",
                }
            ],
        }

        with patch("core.dignity.runtime._run_dignity_turn", return_value=state), patch(
            "core.dignity.runtime.send_stt_message", new=AsyncMock()
        ), patch("core.dignity.runtime._save_interview_audio_segments"), patch(
            "core.dignity.runtime._write_dignity_log"
        ), patch("core.dignity.runtime._write_safety_alert") as save_alert, patch(
            "core.dignity.runtime.send_robot_action_event", new=AsyncMock()
        ), patch("core.dignity.runtime._speak_dignity_reply") as speak, patch(
            "core.dignity.runtime._schedule_background_state_update"
        ) as background_update:
            handled = await handle_dignity_turn_if_active(conn, "我现在就想死。")

        events = [
            json.loads(call.args[0])["event"]
            for call in conn.websocket.send.await_args_list
        ]
        self.assertTrue(handled)
        self.assertEqual(events, ["safety_alert", "turn_result", "mode_paused"])
        self.assertTrue(conn.dignity_paused)
        self.assertEqual(conn.dignity_pause_reason, "safety_L3")
        self.assertEqual(conn.dignity_safety_alert["level"], "L3")
        self.assertEqual(conn.dignity_safety_alert["task"]["priority"], "emergency")
        save_alert.assert_called_once()
        speak.assert_called_once()
        background_update.assert_not_called()

    async def test_level_three_alert_blocks_patient_resume(self):
        conn = build_connection()
        conn.dignity_paused = True
        conn.dignity_safety_alert = {
            "level": "L3",
            "task": {"status": "pending"},
        }

        with patch(
            "core.dignity.runtime.send_robot_action_event", new=AsyncMock()
        ):
            await resume_dignity_mode(conn, {"source": "patient_button"})

        event = json.loads(conn.websocket.send.await_args.args[0])
        self.assertEqual(event["event"], "safety_resume_blocked")
        self.assertTrue(conn.dignity_paused)

    async def test_clinician_release_clears_level_three_hold(self):
        conn = build_connection()
        conn.dignity_paused = True
        conn.dignity_safety_alert = {
            "level": "L3",
            "task": {"status": "pending"},
        }

        with patch(
            "core.dignity.runtime.send_robot_action_event", new=AsyncMock()
        ), patch("core.dignity.runtime._write_safety_alert"), patch(
            "core.dignity.runtime._write_dignity_log"
        ), patch("core.dignity.runtime._speak_dignity_reply"):
            await resume_dignity_mode(conn, {"source": "clinician_release"})

        event = json.loads(conn.websocket.send.await_args.args[0])
        self.assertEqual(event["event"], "mode_resumed")
        self.assertFalse(conn.dignity_paused)
        self.assertIsNone(conn.dignity_safety_alert)

    async def test_safety_task_can_be_acknowledged_and_closed(self):
        conn = build_connection()
        conn.dignity_active = False
        assessment = assess_safety_risk("我觉得活着没意思。")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "core.dignity.runtime.SAFETY_ALERT_DIR", Path(temp_dir)
        ), patch(
            "core.dignity.runtime.send_robot_action_event", new=AsyncMock()
        ), patch("core.dignity.runtime._write_dignity_log"):
            alert = _create_safety_alert(conn, assessment, "我觉得活着没意思。")
            await list_dignity_safety_alerts(conn, {"patient_id": "patient-1"})
            list_event = json.loads(conn.websocket.send.await_args.args[0])
            self.assertEqual(list_event["event"], "safety_alerts_list")
            self.assertEqual(len(list_event["data"]["alerts"]), 1)

            await update_dignity_safety_task(
                conn,
                {
                    "alert_id": alert["alert_id"],
                    "task_action": "acknowledge",
                    "operator": "护士甲",
                    "note": "已查看，准备联系患者。",
                },
            )
            self.assertEqual(_load_safety_alerts(conn)[0]["task"]["status"], "acknowledged")

            await update_dignity_safety_task(
                conn,
                {
                    "alert_id": alert["alert_id"],
                    "task_action": "close",
                    "operator": "护士甲",
                    "note": "已完成复核。",
                },
            )
            saved = _load_safety_alerts(conn)[0]
            self.assertEqual(saved["task"]["status"], "closed")
            self.assertEqual(saved["last_operator"], "护士甲")
            self.assertIsNone(conn.dignity_safety_alert)

    async def test_escalation_pauses_and_clinician_release_resumes(self):
        conn = build_connection()
        assessment = assess_safety_risk("我觉得活着没意思。")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "core.dignity.runtime.SAFETY_ALERT_DIR", Path(temp_dir)
        ), patch(
            "core.dignity.runtime.send_robot_action_event", new=AsyncMock()
        ), patch("core.dignity.runtime._write_dignity_log"), patch(
            "core.dignity.runtime._speak_dignity_reply"
        ):
            alert = _create_safety_alert(conn, assessment, "我觉得活着没意思。")
            await update_dignity_safety_task(
                conn,
                {
                    "alert_id": alert["alert_id"],
                    "task_action": "escalate",
                    "operator": "医生乙",
                },
            )
            self.assertTrue(conn.dignity_paused)
            self.assertEqual(conn.dignity_safety_alert["level"], "L3")

            await update_dignity_safety_task(
                conn,
                {
                    "alert_id": alert["alert_id"],
                    "task_action": "release",
                    "operator": "医生乙",
                    "note": "已当面核实安全。",
                },
            )
            saved = _load_safety_alerts(conn)[0]
            self.assertEqual(saved["task"]["status"], "released")
            self.assertFalse(conn.dignity_paused)
            self.assertIsNone(conn.dignity_safety_alert)


if __name__ == "__main__":
    unittest.main()
