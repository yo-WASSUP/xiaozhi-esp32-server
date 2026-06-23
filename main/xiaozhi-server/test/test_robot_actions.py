import json
import unittest

from core.robot_actions.adapter import dispatch_robot_action
from core.robot_actions.classifier import classify_robot_action_by_rule


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class FakeLogger:
    def bind(self, **kwargs):
        return self

    def info(self, message):
        pass


class FakeConn:
    def __init__(self):
        self.session_id = "test-session"
        self.websocket = FakeWebSocket()
        self.logger = FakeLogger()


class RobotActionTests(unittest.IsolatedAsyncioTestCase):
    def test_rule_classifier_maps_common_voice_commands(self):
        self.assertEqual(
            classify_robot_action_by_rule("你过来一点")["action_id"],
            "base.forward",
        )
        self.assertEqual(
            classify_robot_action_by_rule("挥挥手打个招呼")["action_id"],
            "arm.wave",
        )
        self.assertEqual(
            classify_robot_action_by_rule("停一下别动")["action_id"],
            "system.stop",
        )

    def test_example_classifier_handles_semantic_variants(self):
        self.assertEqual(
            classify_robot_action_by_rule("我看不清你")["action_id"],
            "base.forward",
        )
        self.assertEqual(
            classify_robot_action_by_rule("能不能靠我近一点")["action_id"],
            "base.forward",
        )
        self.assertEqual(
            classify_robot_action_by_rule("有点难过你安慰一下")["action_id"],
            "arm.comfort",
        )

    def test_classifier_ignores_normal_conversation(self):
        self.assertIsNone(classify_robot_action_by_rule("我小时候在学校停过一年课"))
        self.assertIsNone(classify_robot_action_by_rule("今天恢复得还可以"))

    async def test_adapter_sends_standard_robot_action_event(self):
        conn = FakeConn()

        result = await dispatch_robot_action(
            conn,
            {
                "action_id": "base.forward",
                "source": "voice_rule",
                "reason": "test",
                "params": {},
            },
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["action_id"], "base.forward")
        self.assertEqual(result["params"]["speed"], 0.2)
        self.assertEqual(result["params"]["duration_ms"], 800)
        payload = json.loads(conn.websocket.messages[-1])
        self.assertEqual(payload["type"], "client_action")
        self.assertEqual(payload["action"], "robot_action")
        self.assertEqual(payload["action_id"], "base.forward")

    async def test_adapter_rejects_movement_during_emergency_stop(self):
        conn = FakeConn()
        conn.robot_emergency_stop = True

        result = await dispatch_robot_action(
            conn,
            {
                "action_id": "base.forward",
                "source": "voice_rule",
                "params": {},
            },
        )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["rejected_reason"], "emergency stop active")


if __name__ == "__main__":
    unittest.main()
