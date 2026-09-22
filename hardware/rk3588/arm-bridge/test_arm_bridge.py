import argparse
import json
import sys
import types
import unittest
from unittest.mock import patch

fake_mqtt_module = types.ModuleType("paho.mqtt.client")
fake_mqtt_module.Client = object
sys.modules.setdefault("paho", types.ModuleType("paho"))
sys.modules.setdefault("paho.mqtt", types.ModuleType("paho.mqtt"))
sys.modules.setdefault("paho.mqtt.client", fake_mqtt_module)

from arm_bridge import ArmBridge


class FakeMqttClient:
    def __init__(self):
        self.published = []

    def username_pw_set(self, username, password):
        pass

    def tls_set(self):
        pass

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, json.loads(payload), qos, retain))


class ArmBridgeTests(unittest.TestCase):
    def test_bridge_defaults_wave_to_right_side(self):
        client = FakeMqttClient()
        args = argparse.Namespace(
            client_id="test-arm-bridge",
            username="",
            password="",
            tls=False,
            device_id="rk3588-eye-001",
            status_topic="robot/rk3588-eye-001/arm/status",
            qos=0,
        )

        with patch("arm_bridge.mqtt.Client", return_value=client):
            bridge = ArmBridge(args)

        message = argparse.Namespace(
            payload=json.dumps(
                {
                    "action_id": "arm.wave",
                    "params": {
                        "repeat": 1,
                        "duration_ms": 1500,
                    },
                }
            ).encode("utf-8")
        )
        bridge.on_message(client, None, message)

        self.assertEqual(bridge.current_params["side"], "right")

    def test_bridge_defaults_non_wave_actions_to_both_sides(self):
        client = FakeMqttClient()
        args = argparse.Namespace(
            client_id="test-arm-bridge",
            username="",
            password="",
            tls=False,
            device_id="rk3588-eye-001",
            status_topic="robot/rk3588-eye-001/arm/status",
            qos=0,
        )

        with patch("arm_bridge.mqtt.Client", return_value=client):
            bridge = ArmBridge(args)

        message = argparse.Namespace(
            payload=json.dumps(
                {
                    "action_id": "arm.gentle",
                    "params": {
                        "repeat": 1,
                        "duration_ms": 1000,
                    },
                }
            ).encode("utf-8")
        )
        bridge.on_message(client, None, message)

        self.assertEqual(bridge.current_params["side"], "both")

    def test_bridge_accepts_both_sides(self):
        client = FakeMqttClient()
        args = argparse.Namespace(
            client_id="test-arm-bridge",
            username="",
            password="",
            tls=False,
            device_id="rk3588-eye-001",
            status_topic="robot/rk3588-eye-001/arm/status",
            qos=0,
        )

        with patch("arm_bridge.mqtt.Client", return_value=client):
            bridge = ArmBridge(args)

        message = argparse.Namespace(
            payload=json.dumps(
                {
                    "action_id": "arm.wave",
                    "params": {
                        "side": "both",
                        "repeat": 1,
                        "duration_ms": 1500,
                    },
                }
            ).encode("utf-8")
        )
        bridge.on_message(client, None, message)

        self.assertEqual(bridge.current_params["side"], "both")
        self.assertIsNone(client.published[-1][1]["last_error"])


if __name__ == "__main__":
    unittest.main()
