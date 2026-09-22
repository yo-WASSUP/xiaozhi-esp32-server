import asyncio
import json
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from core.dignity.robot_eye import RobotEyeMqttPublisher, build_eye_command_payload
from core.robot_actions.adapter import dispatch_robot_action
from core.robot_actions.classifier import (
    classify_robot_action,
    classify_robot_action_by_rule,
)
from core.robot_actions.drivers.arm_mqtt import (
    RobotArmMqttPublisher,
    _config_key as arm_mqtt_config_key,
)
from core.robot_actions.drivers.aroma_mqtt import (
    RobotAromaMqttPublisher,
    build_aroma_command_payload,
)
from core.robot_actions.drivers.base_slamware import (
    DEFAULT_CONFIG as BASE_SLAMWARE_DEFAULT_CONFIG,
    _build_go_home_payload,
    _build_move_by_payload,
    _build_rotate_payload,
    _poi_name_matches,
)
from core.robot_actions.drivers.bed_mqtt import (
    RobotBedMqttPublisher,
    build_bed_command_payload,
)


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.debugs = []
        self.warnings = []

    def bind(self, **kwargs):
        return self

    def opt(self, **kwargs):
        return self

    def info(self, message):
        self.infos.append(message)

    def debug(self, message):
        self.debugs.append(message)

    def warning(self, message):
        self.warnings.append(message)


class FakeMqttPublishInfo:
    def __init__(self, published=True, error=None):
        self._published = published
        self._error = error

    def wait_for_publish(self, timeout=None):
        if self._error:
            raise self._error

    def is_published(self):
        return self._published


class FakeMqttClient:
    def __init__(self, client_id, *, connected_on_loop_start=True):
        self.client_id = client_id
        self.connected_on_loop_start = connected_on_loop_start
        self.connected = False
        self.connect_calls = 0
        self.connect_args = None
        self.published = []

    def connect(self, host, port, keepalive):
        self.connect_calls += 1
        self.connect_args = (host, port, keepalive)
        return 0

    def loop_start(self):
        if self.connected_on_loop_start:
            self.connected = True

    def loop_stop(self):
        pass

    def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        if not self.connected:
            return FakeMqttPublishInfo(
                published=False,
                error=RuntimeError(
                    "Message publish failed: The client is not currently connected."
                ),
            )
        return FakeMqttPublishInfo()


@contextmanager
def fake_paho_client_factory(factory):
    paho_module = types.ModuleType("paho")
    paho_module.__path__ = []
    mqtt_module = types.ModuleType("paho.mqtt")
    mqtt_module.__path__ = []
    client_module = types.ModuleType("paho.mqtt.client")
    client_module.Client = factory
    paho_module.mqtt = mqtt_module
    mqtt_module.client = client_module
    with patch.dict(
        sys.modules,
        {
            "paho": paho_module,
            "paho.mqtt": mqtt_module,
            "paho.mqtt.client": client_module,
        },
    ):
        yield


class FakeConn:
    def __init__(self):
        self.session_id = "test-session"
        self.websocket = FakeWebSocket()
        self.logger = FakeLogger()
        self.config = {}


class RobotActionTests(unittest.IsolatedAsyncioTestCase):
    def test_eye_and_arm_mqtt_publishers_use_distinct_default_client_ids(self):
        created_clients = []

        def create_client(*args, **kwargs):
            client = FakeMqttClient(kwargs["client_id"])
            created_clients.append(client)
            return client

        config = {
            "device_id": "rk3588-eye-001",
            "broker_host": "127.0.0.1",
            "broker_port": 1883,
        }
        with fake_paho_client_factory(create_client):
            RobotEyeMqttPublisher()._ensure_client(config)
            RobotArmMqttPublisher()._ensure_client(config)

        self.assertEqual(len(created_clients), 2)
        self.assertNotEqual(
            created_clients[0].client_id,
            created_clients[1].client_id,
        )

    def test_arm_mqtt_publisher_waits_for_connection_before_returning_client(self):
        class DelayedConnectClient(FakeMqttClient):
            def __init__(self, client_id):
                super().__init__(client_id, connected_on_loop_start=False)
                self.connection_checks = 0
                self.loop_started = False

            def loop_start(self):
                self.loop_started = True

            def is_connected(self):
                self.connection_checks += 1
                if self.loop_started and self.connection_checks >= 2:
                    self.connected = True
                return self.connected

        client = DelayedConnectClient("test-arm")
        with fake_paho_client_factory(lambda *args, **kwargs: client):
            returned = RobotArmMqttPublisher()._ensure_client(
                {
                    "device_id": "rk3588-eye-001",
                    "broker_host": "127.0.0.1",
                    "broker_port": 1883,
                    "connect_timeout_seconds": 0.1,
                }
            )

        self.assertIs(returned, client)
        self.assertTrue(client.is_connected())

    def test_arm_mqtt_publisher_reconnects_before_publish_when_cached_client_disconnected(
        self,
    ):
        arm_config = {
            "enabled": True,
            "device_id": "rk3588-eye-001",
            "broker_host": "127.0.0.1",
            "broker_port": 1883,
            "command_topic": "robot/rk3588-eye-001/arm/cmd",
        }
        disconnected_client = FakeMqttClient(
            "xiaozhi-server-rk3588-eye-001",
            connected_on_loop_start=False,
        )
        reconnected_client = FakeMqttClient("xiaozhi-server-rk3588-eye-001-arm")
        publisher = RobotArmMqttPublisher()
        publisher._client = disconnected_client
        publisher._config_key = arm_mqtt_config_key(arm_config)
        logger = FakeLogger()

        with fake_paho_client_factory(lambda *args, **kwargs: reconnected_client):
            publisher.publish(
                {"hospice": {"robot_arm": arm_config}},
                {"action_id": "arm.wave"},
                logger=logger,
            )

        self.assertEqual(logger.warnings, [])
        self.assertEqual(reconnected_client.connect_calls, 1)
        self.assertEqual(len(reconnected_client.published), 1)
        self.assertIn(
            "机械臂 MQTT 发布成功: topic=robot/rk3588-eye-001/arm/cmd, "
            'action_id=arm.wave, params={}',
            logger.debugs,
        )

    def test_eye_mqtt_publisher_logs_complete_success_details(self):
        eye_config = {
            "enabled": True,
            "device_id": "rk3588-eye-001",
            "broker_host": "127.0.0.1",
            "broker_port": 1883,
            "command_topic": "robot/rk3588-eye-001/eye/cmd",
        }
        client = FakeMqttClient("test-eye")
        logger = FakeLogger()

        with fake_paho_client_factory(lambda *args, **kwargs: client):
            RobotEyeMqttPublisher().publish(
                {"hospice": {"robot_eye": eye_config}},
                {
                    "action_id": "eye.gentle",
                    "origin_action_id": "arm.comfort",
                    "robot_action": "comfort",
                },
                logger=logger,
            )

        self.assertIn(
            "眼睛表情 MQTT 发布成功: topic=robot/rk3588-eye-001/eye/cmd, "
            "action_id=eye.gentle, origin_action_id=arm.comfort, "
            "robot_action=comfort",
            logger.debugs,
        )

    def test_aroma_mqtt_publisher_logs_complete_success_details(self):
        aroma_config = {
            "enabled": True,
            "device_id": "rk3588-eye-001",
            "broker_host": "127.0.0.1",
            "broker_port": 1883,
            "command_topic": "robot/rk3588-eye-001/aroma/cmd",
        }
        client = FakeMqttClient("test-aroma")
        logger = FakeLogger()

        with fake_paho_client_factory(lambda *args, **kwargs: client):
            RobotAromaMqttPublisher().publish(
                {"hospice": {"robot_aroma": aroma_config}},
                {
                    "action_id": "aroma.start",
                    "params": {"type": "1", "duration_ms": 60000},
                },
                logger=logger,
            )

        self.assertIn(
            "香薰 MQTT 发布成功: topic=robot/rk3588-eye-001/aroma/cmd, "
            'action_id=aroma.start, params={"duration_ms":60000,"type":"1"}',
            logger.debugs,
        )

    def test_bed_mqtt_publisher_uses_independent_rk3588_host(self):
        bed_config = {
            "enabled": True,
            "device_id": "rk3588-bed-001",
            "broker_host": "10.0.2.244",
            "broker_port": 1883,
            "command_topic": "robot/rk3588-bed-001/bed/cmd",
        }
        client = FakeMqttClient("test-bed")
        logger = FakeLogger()

        with fake_paho_client_factory(lambda *args, **kwargs: client):
            RobotBedMqttPublisher().publish(
                {"hospice": {"robot_bed": bed_config}},
                {"action_id": "bed.head.up", "params": {}},
                logger=logger,
            )

        self.assertEqual(client.connect_args, ("10.0.2.244", 1883, 30))
        self.assertEqual(len(client.published), 1)
        self.assertIn(
            "医疗床 MQTT 发布成功: topic=robot/rk3588-bed-001/bed/cmd, "
            "action_id=bed.head.up",
            logger.debugs,
        )

    def test_rule_classifier_maps_common_voice_commands(self):
        self.assertEqual(
            classify_robot_action_by_rule("你过来一点")["action_id"],
            "base.forward",
        )
        precise_move = classify_robot_action_by_rule("机器人向前0.2米")
        self.assertEqual(precise_move["action_id"], "base.forward")
        self.assertEqual(precise_move["params"]["distance_m"], 0.2)
        precise_turn = classify_robot_action_by_rule("机器人右转15度")
        self.assertEqual(precise_turn["action_id"], "base.turn_right")
        self.assertEqual(precise_turn["params"]["angle"], 15)
        chinese_precise_turn = classify_robot_action_by_rule("机器人左转五度")
        self.assertEqual(chinese_precise_turn["action_id"], "base.turn_left")
        self.assertEqual(chinese_precise_turn["params"]["angle"], 5)
        chinese_two_digit_turn = classify_robot_action_by_rule("机器人右转十五度")
        self.assertEqual(chinese_two_digit_turn["action_id"], "base.turn_right")
        self.assertEqual(chinese_two_digit_turn["params"]["angle"], 15)
        navigation = classify_robot_action_by_rule("机器人去一号测试点位")
        self.assertEqual(navigation["action_id"], "base.move")
        self.assertEqual(navigation["params"]["target_name"], "一号测试点位")
        navigation_with_prefix = classify_robot_action_by_rule("导航去一号测试点位")
        self.assertEqual(navigation_with_prefix["action_id"], "base.move")
        self.assertEqual(navigation_with_prefix["params"]["target_name"], "一号测试点位")
        split_navigation = classify_robot_action_by_rule("机器人导航。去一号测试点位。")
        self.assertEqual(split_navigation["action_id"], "base.move")
        self.assertEqual(split_navigation["params"]["target_name"], "一号测试点位")
        self.assertEqual(
            classify_robot_action_by_rule("挥挥手打个招呼")["action_id"],
            "arm.wave",
        )
        self.assertEqual(
            classify_robot_action_by_rule("回充电桩")["action_id"],
            "base.homedock",
        )
        self.assertEqual(
            classify_robot_action_by_rule("停一下别动")["action_id"],
            "system.stop",
        )

    def test_rule_classifier_maps_all_medical_bed_commands(self):
        cases = {
            "床头1档位": "bed.head.1",
            "床头2档位": "bed.head.2",
            "床头3档位": "bed.head.3",
            "床头上升一点": "bed.head.up",
            "床头下降一点": "bed.head.down",
            "床头停止运动": "bed.head.stop",
            "床头复位": "bed.head.reset",
            "床尾1档位": "bed.feet.1",
            "床尾2档位": "bed.feet.2",
            "床尾3档位": "bed.feet.3",
            "床尾上升一点": "bed.feet.up",
            "床尾下降一点": "bed.feet.down",
            "床尾停止运动": "bed.feet.stop",
            "床尾复位": "bed.feet.reset",
        }
        for text, expected_action_id in cases.items():
            with self.subTest(text=text):
                action = classify_robot_action_by_rule(text)
                self.assertIsNotNone(action)
                self.assertEqual(action["action_id"], expected_action_id)

    def test_bed_action_table_phrases_use_exact_whitelist(self):
        cases = {
            "床头升高": "bed.head.up",
            "床头降低": "bed.head.down",
            "床尾升高": "bed.feet.up",
            "床尾降低": "bed.feet.down",
        }
        for text, expected_action_id in cases.items():
            with self.subTest(text=text):
                action = classify_robot_action_by_rule(text)
                self.assertIsNotNone(action)
                self.assertEqual(action["action_id"], expected_action_id)
                self.assertEqual(action["source"], "voice_example")

    def test_bed_reset_phrases_take_priority_over_generic_arm_reset(self):
        cases = {
            "请帮我床头复位": "bed.head.reset",
            "请帮我床尾复位": "bed.feet.reset",
            "复位床头。": "bed.head.reset",
            "复位床尾。": "bed.feet.reset",
            "请帮我复位床尾": "bed.feet.reset",
            "复位": "arm.reset",
            "床头复位，马上停": "system.stop",
        }
        for text, action_id in cases.items():
            with self.subTest(text=text):
                action = classify_robot_action_by_rule(text)
                self.assertIsNotNone(action)
                self.assertEqual(action["action_id"], action_id)

    def test_physical_action_near_miss_does_not_execute_by_similarity(self):
        self.assertIsNone(classify_robot_action_by_rule("床头升温一点"))

    async def test_non_whitelisted_hardware_phrase_does_not_use_llm_to_execute(self):
        class HardwareGuessingLLM:
            def __init__(self):
                self.calls = 0

            def response_no_stream(self, *args, **kwargs):
                self.calls += 1
                return '{"action_id":"bed.head.up","reason":"猜测"}'

        conn = FakeConn()
        conn.llm = HardwareGuessingLLM()

        action = await classify_robot_action(conn, "床头升温一点")

        self.assertIsNone(action)
        self.assertEqual(conn.llm.calls, 0)

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

    def test_example_classifier_ignores_short_fragments_of_commands(self):
        for text in ("我。", "你。", "离。", "近。", "一点。"):
            with self.subTest(text=text):
                self.assertIsNone(classify_robot_action_by_rule(text))

    def test_voice_arm_action_uses_explicit_left_side(self):
        action = classify_robot_action_by_rule("挥动左手")

        self.assertEqual(action["action_id"], "arm.wave")
        self.assertEqual(action["params"]["side"], "left")

    def test_voice_arm_action_uses_explicit_right_side(self):
        action = classify_robot_action_by_rule("挥动右手")

        self.assertEqual(action["action_id"], "arm.wave")
        self.assertEqual(action["params"]["side"], "right")

    def test_voice_wave_uses_right_side_when_direction_is_omitted(self):
        action = classify_robot_action_by_rule("挥挥手")

        self.assertEqual(action["action_id"], "arm.wave")
        self.assertEqual(action["params"]["side"], "right")

    def test_voice_non_wave_arm_action_uses_both_sides_when_direction_is_omitted(self):
        action = classify_robot_action_by_rule("轻轻动一下")

        self.assertEqual(action["action_id"], "arm.gentle")
        self.assertEqual(action["params"]["side"], "both")

    def test_voice_arm_action_uses_both_sides_when_left_and_right_are_spoken(self):
        action = classify_robot_action_by_rule("左右手一起挥动")

        self.assertEqual(action["action_id"], "arm.wave")
        self.assertEqual(action["params"]["side"], "both")

    def test_classifier_ignores_normal_conversation(self):
        self.assertIsNone(classify_robot_action_by_rule("我小时候在学校停过一年课"))
        self.assertIsNone(classify_robot_action_by_rule("今天恢复得还可以"))
        self.assertIsNone(classify_robot_action_by_rule("换个位置"))
        self.assertIsNone(classify_robot_action_by_rule("我不想去医院"))
        self.assertIsNone(classify_robot_action_by_rule("今天想去公园走走"))

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
        self.assertIn("event_time", payload)
        self.assertIn(
            "<bold><light-magenta>机器人动作事件: "
            "action_id=base.forward, module=base, "
            "status=accepted, source=voice_rule, source_event=voice_action, "
            'params={"duration_ms":800,"speed":0.2}, reason="test", '
            'rejected_reason=""</light-magenta></bold>',
            conn.logger.infos,
        )

    async def test_adapter_derives_duration_from_distance(self):
        conn = FakeConn()

        result = await dispatch_robot_action(
            conn,
            {
                "action_id": "base.forward",
                "source": "voice_rule",
                "reason": "test",
                "params": {"distance_m": 0.2},
            },
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["params"]["speed"], 0.2)
        self.assertEqual(result["params"]["distance_m"], 0.2)
        self.assertEqual(result["params"]["duration_ms"], 1000)

    async def test_voice_distance_in_centimeters_drives_short_move(self):
        conn = FakeConn()
        action = classify_robot_action_by_rule("机器人往前十厘米")

        result = await dispatch_robot_action(conn, action)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["action_id"], "base.forward")
        self.assertAlmostEqual(result["params"]["distance_m"], 0.1)
        self.assertEqual(result["params"]["duration_ms"], 500)

    async def test_wave_action_without_side_defaults_to_right_side(self):
        conn = FakeConn()

        result = await dispatch_robot_action(
            conn,
            {
                "action_id": "arm.wave",
                "source": "system",
                "params": {},
            },
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["params"]["side"], "right")

    async def test_non_wave_arm_actions_without_side_default_to_both_sides(self):
        for action_id in ("arm.gentle", "arm.comfort", "arm.reset"):
            with self.subTest(action_id=action_id):
                result = await dispatch_robot_action(
                    FakeConn(),
                    {
                        "action_id": action_id,
                        "source": "system",
                        "params": {},
                    },
                )

                self.assertEqual(result["status"], "accepted")
                self.assertEqual(result["params"]["side"], "both")

    async def test_invalid_arm_side_uses_the_action_default(self):
        wave = await dispatch_robot_action(
            FakeConn(),
            {
                "action_id": "arm.wave",
                "source": "system",
                "params": {"side": "invalid"},
            },
        )
        gentle = await dispatch_robot_action(
            FakeConn(),
            {
                "action_id": "arm.gentle",
                "source": "system",
                "params": {"side": "invalid"},
            },
        )

        self.assertEqual(wave["params"]["side"], "right")
        self.assertEqual(gentle["params"]["side"], "both")

    async def test_voice_arm_action_publishes_selected_sides_to_rk3588(self):
        conn = FakeConn()
        conn.config = {
            "hospice": {
                "robot_arm": {
                    "enabled": True,
                    "device_id": "rk3588-eye-001",
                }
            }
        }
        action = classify_robot_action_by_rule("左右手一起挥动")

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch(
                "core.robot_actions.drivers.arm_mqtt.is_robot_arm_enabled",
                return_value=True,
            ),
            patch(
                "core.robot_actions.drivers.arm_mqtt.publish_robot_arm_command"
            ) as publish,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(conn, action)
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        publish.assert_called_once()
        payload = publish.call_args.args[1]
        self.assertEqual(payload["action_id"], "arm.wave")
        self.assertEqual(payload["params"]["side"], "both")
        self.assertIn(
            "机械臂动作 MQTT 发布已调度: action_id=arm.wave, "
            'params={"duration_ms":1500,"repeat":1,"side":"both"}',
            conn.logger.debugs,
        )

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

    async def test_adapter_publishes_eye_action_to_rk3588_payload(self):
        conn = FakeConn()
        conn.config = {"hospice": {"robot_eye": {"enabled": True, "device_id": "rk3588-eye-001"}}}

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("core.dignity.robot_eye.is_robot_eye_enabled", return_value=True),
            patch(
                "core.dignity.robot_eye.build_eye_command_payload",
                return_value={"type": "eye.set", "action_id": "eye.gentle"},
            ) as build_payload,
            patch("core.dignity.robot_eye.publish_robot_eye_command") as publish,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(
                conn,
                {
                    "action_id": "eye.gentle",
                    "source": "voice_rule",
                    "params": {},
                },
            )
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        build_payload.assert_called_once()
        self.assertEqual(build_payload.call_args.args[3], "comfort")
        self.assertEqual(build_payload.call_args.kwargs["action_id"], "eye.gentle")
        self.assertEqual(build_payload.call_args.kwargs["origin_action_id"], "eye.gentle")
        self.assertTrue(build_payload.call_args.kwargs["event_time"])
        publish.assert_called_once()
        self.assertIn(
            "眼睛动作 MQTT 发布已调度: action_id=eye.gentle, "
            "robot_action=comfort",
            conn.logger.debugs,
        )

    async def test_adapter_executes_base_driver_when_enabled(self):
        conn = FakeConn()
        conn.config = {
            "hospice": {
                "robot_base": {
                    "enabled": True,
                    "driver": "slamware",
                    "base_url": "http://10.0.2.15:1448",
                }
            }
        }

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("core.robot_actions.drivers.base_slamware.is_robot_base_enabled", return_value=True),
            patch(
                "core.robot_actions.drivers.base_slamware.execute_robot_base_action",
                return_value={
                    "action_id": "base.forward",
                    "module": "base",
                    "status": "executed",
                    "message": "ok",
                },
            ) as execute_base,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(
                conn,
                {
                    "action_id": "base.forward",
                    "source": "voice_rule",
                    "params": {"distance_m": 0.2},
                },
            )
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        execute_base.assert_called_once()
        self.assertEqual(execute_base.call_args.args[1]["action_id"], "base.forward")
        self.assertEqual(execute_base.call_args.args[1]["params"]["distance_m"], 0.2)

    async def test_numbered_aroma_voice_command_reaches_mqtt(self):
        conn = FakeConn()
        conn.config = {"hospice": {"robot_aroma": {"enabled": True}}}

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        for number, aroma_type in (("一", "1"), ("二", "2"), ("三", "3"), ("1", "1"), ("2", "2"), ("3", "3")):
            for verb in ("开启", "打开", "开"):
                with self.subTest(number=number, verb=verb):
                    action = await classify_robot_action(conn, f"{verb}{number}号香薰。")
                    self.assertIsNotNone(action)
                    with (
                        patch("core.robot_actions.drivers.aroma_mqtt.publish_robot_aroma_command") as publish,
                        patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
                    ):
                        result = await dispatch_robot_action(conn, action, source_event="voice_action")
                        await asyncio.sleep(0)
                    self.assertEqual(result["status"], "accepted")
                    publish.assert_called_once()
                    payload = publish.call_args.args[1]
                    self.assertEqual(payload["action_id"], "aroma.start")
                    self.assertEqual(payload["params"], {"type": aroma_type, "duration_ms": 60000})

    def test_numbered_aroma_mention_does_not_start_device(self):
        for text in ("一号香薰是什么", "开启四号香薰", "不要开启一号香薰", "开启一号香薰了吗"):
            with self.subTest(text=text):
                self.assertIsNone(classify_robot_action_by_rule(text))

    async def test_documented_aroma_commands_reach_mqtt(self):
        conn = FakeConn()
        conn.config = {"hospice": {"robot_aroma": {"enabled": True}}}

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        cases = [
            ("打开2号香熏5分钟", "aroma.start", {"type": "2", "duration_ms": 300000}),
            ("打开三号香薰两分钟", "aroma.start", {"type": "3", "duration_ms": 120000}),
            ("打开一号香熏三十一分钟", "aroma.start", {"type": "1", "duration_ms": 1800000}),
            ("打开香薰", "aroma.start", {"type": "1", "duration_ms": 60000}),
        ]
        cases.extend((text, "aroma.stop", {}) for text in ("关闭香熏", "关掉香薰", "不要香味", "停止香薰", "关闭所有香薰"))
        cases.extend((text, "aroma.scene_relax", {"type": "1", "duration_ms": 60000}) for text in ("放松一下", "安抚", "睡前", "紧张", "我有点紧张"))
        for text, action_id, params in cases:
            with self.subTest(text=text):
                action = await classify_robot_action(conn, text)
                self.assertIsNotNone(action)
                with (
                    patch("core.robot_actions.drivers.aroma_mqtt.publish_robot_aroma_command") as publish,
                    patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
                ):
                    result = await dispatch_robot_action(conn, action, source_event="voice_action")
                    await asyncio.sleep(0)
                self.assertEqual(result["status"], "accepted")
                publish.assert_called_once()
                self.assertEqual(publish.call_args.args[1]["action_id"], action_id)
                self.assertEqual(publish.call_args.args[1]["params"], params)

    def test_aroma_invalid_or_negated_commands_do_not_start(self):
        for text in ("打开香薰五分钟了吗", "不要打开香薰", "不要放松一下", "打开香薰负二分钟", "打开香薰abc分钟"):
            with self.subTest(text=text):
                self.assertIsNone(classify_robot_action_by_rule(text))

    async def test_zero_aroma_voice_duration_is_rejected(self):
        conn = FakeConn()
        action = await classify_robot_action(conn, "打开一号香熏零分钟")
        self.assertIsNotNone(action)
        result = await dispatch_robot_action(conn, action)
        self.assertNotEqual(result["status"], "accepted")

    async def test_adapter_publishes_aroma_action_with_default_params(self):
        conn = FakeConn()
        conn.config = {
            "hospice": {
                "robot_aroma": {
                    "enabled": True,
                    "device_id": "rk3588-eye-001",
                }
            }
        }

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch(
                "core.robot_actions.drivers.aroma_mqtt.is_robot_aroma_enabled",
                return_value=True,
            ),
            patch(
                "core.robot_actions.drivers.aroma_mqtt.publish_robot_aroma_command"
            ) as publish,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(
                conn,
                {
                    "action_id": "aroma.start",
                    "source": "voice_rule",
                    "params": {},
                },
            )
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["params"], {"type": "1", "duration_ms": 60000})
        publish.assert_called_once()
        published_payload = publish.call_args.args[1]
        self.assertEqual(published_payload["type"], "aroma.set")
        self.assertEqual(published_payload["action_id"], "aroma.start")
        self.assertEqual(published_payload["params"], {"type": "1", "duration_ms": 60000})
        self.assertIn(
            "香薰动作 MQTT 发布已调度: action_id=aroma.start, "
            'params={"duration_ms":60000,"type":"1"}',
            conn.logger.debugs,
        )

    async def test_adapter_validates_aroma_params(self):
        conn = FakeConn()

        invalid_type = await dispatch_robot_action(
            conn,
            {
                "action_id": "aroma.start",
                "source": "voice_rule",
                "params": {"type": "9"},
            },
        )
        invalid_scene_type = await dispatch_robot_action(
            conn,
            {
                "action_id": "aroma.scene_relax",
                "source": "voice_rule",
                "params": {"type": "2"},
            },
        )
        invalid_duration = await dispatch_robot_action(
            conn,
            {
                "action_id": "aroma.start",
                "source": "voice_rule",
                "params": {"duration_ms": 0},
            },
        )
        clamped_duration = await dispatch_robot_action(
            conn,
            {
                "action_id": "aroma.start",
                "source": "voice_rule",
                "params": {"duration_ms": 500},
            },
        )
        clamped_max_duration = await dispatch_robot_action(
            conn,
            {
                "action_id": "aroma.start",
                "source": "voice_rule",
                "params": {"duration_ms": 1900000},
            },
        )

        self.assertEqual(invalid_type["status"], "rejected")
        self.assertEqual(invalid_scene_type["status"], "rejected")
        self.assertEqual(invalid_duration["status"], "rejected")
        self.assertEqual(clamped_duration["status"], "accepted")
        self.assertEqual(clamped_duration["params"]["duration_ms"], 1000)
        self.assertEqual(clamped_max_duration["status"], "accepted")
        self.assertEqual(clamped_max_duration["params"]["duration_ms"], 1800000)

    async def test_emergency_stop_allows_only_aroma_stop(self):
        conn = FakeConn()
        conn.robot_emergency_stop = True

        start_result = await dispatch_robot_action(
            conn,
            {"action_id": "aroma.start", "source": "voice_rule", "params": {}},
        )
        stop_result = await dispatch_robot_action(
            conn,
            {"action_id": "aroma.stop", "source": "voice_rule", "params": {}},
        )

        self.assertEqual(start_result["status"], "rejected")
        self.assertEqual(stop_result["status"], "accepted")

    async def test_system_stop_publishes_aroma_stop(self):
        conn = FakeConn()
        conn.config = {"hospice": {"robot_aroma": {"enabled": True}}}

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch(
                "core.robot_actions.drivers.aroma_mqtt.is_robot_aroma_enabled",
                return_value=True,
            ),
            patch(
                "core.robot_actions.drivers.aroma_mqtt.publish_robot_aroma_command"
            ) as publish,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(
                conn,
                {"action_id": "system.stop", "source": "voice_rule", "params": {}},
            )
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        publish.assert_called_once()
        published_payload = publish.call_args.args[1]
        self.assertEqual(published_payload["action_id"], "aroma.stop")
        self.assertEqual(published_payload["params"], {})

    async def test_adapter_publishes_bed_action_to_independent_rk3588(self):
        conn = FakeConn()
        conn.config = {
            "hospice": {
                "robot_bed": {
                    "enabled": True,
                    "device_id": "rk3588-bed-001",
                    "broker_host": "10.0.2.244",
                }
            }
        }

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch(
                "core.robot_actions.drivers.bed_mqtt.is_robot_bed_enabled",
                return_value=True,
            ),
            patch(
                "core.robot_actions.drivers.bed_mqtt.publish_robot_bed_command"
            ) as publish,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(
                conn,
                {
                    "action_id": "bed.head.up",
                    "source": "voice_example",
                    "params": {"ignored": True},
                },
            )
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["params"], {})
        publish.assert_called_once()
        published_payload = publish.call_args.args[1]
        self.assertEqual(published_payload["type"], "bed.set")
        self.assertEqual(published_payload["device_id"], "rk3588-bed-001")
        self.assertEqual(published_payload["action_id"], "bed.head.up")
        self.assertEqual(published_payload["module"], "bed")
        self.assertEqual(published_payload["params"], {})

    async def test_bed_reset_voice_commands_publish_and_respect_emergency_stop(self):
        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        for text, action_id in (
            ("床头复位", "bed.head.reset"),
            ("床尾复位", "bed.feet.reset"),
            ("复位床头。", "bed.head.reset"),
            ("复位床尾。", "bed.feet.reset"),
        ):
            for emergency_stop in (False, True):
                with self.subTest(text=text, emergency_stop=emergency_stop):
                    conn = FakeConn()
                    conn.config = {"hospice": {"robot_bed": {"enabled": True}}}
                    conn.robot_emergency_stop = emergency_stop
                    action = await classify_robot_action(conn, text)
                    self.assertIsNotNone(action)
                    with (
                        patch(
                            "core.robot_actions.drivers.bed_mqtt.publish_robot_bed_command"
                        ) as publish,
                        patch(
                            "core.robot_actions.adapter.asyncio.to_thread",
                            side_effect=run_inline,
                        ),
                    ):
                        result = await dispatch_robot_action(conn, action)
                        await asyncio.sleep(0)

                    if emergency_stop:
                        self.assertEqual(result["status"], "rejected")
                        self.assertEqual(result["rejected_reason"], "emergency stop active")
                        publish.assert_not_called()
                    else:
                        self.assertEqual(result["status"], "accepted")
                        publish.assert_called_once()
                        payload = publish.call_args.args[1]
                        self.assertEqual(payload["type"], "bed.set")
                        self.assertEqual(payload["action_id"], action_id)
                        self.assertEqual(payload["params"], {})

    async def test_system_stop_publishes_both_bed_stop_actions(self):
        conn = FakeConn()
        conn.config = {"hospice": {"robot_bed": {"enabled": True}}}

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch(
                "core.robot_actions.drivers.bed_mqtt.is_robot_bed_enabled",
                return_value=True,
            ),
            patch(
                "core.robot_actions.drivers.bed_mqtt.publish_robot_bed_command"
            ) as publish,
            patch("core.robot_actions.adapter.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await dispatch_robot_action(
                conn,
                {"action_id": "system.stop", "source": "voice_rule", "params": {}},
            )
            await asyncio.sleep(0)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(publish.call_count, 2)
        published_action_ids = [call.args[1]["action_id"] for call in publish.call_args_list]
        self.assertEqual(published_action_ids, ["bed.head.stop", "bed.feet.stop"])
        self.assertTrue(
            all(
                call.args[1]["origin_action_id"] == "system.stop"
                for call in publish.call_args_list
            )
        )

    async def test_emergency_stop_allows_individual_bed_stop_actions(self):
        for action_id in ("bed.head.stop", "bed.feet.stop"):
            with self.subTest(action_id=action_id):
                conn = FakeConn()
                conn.robot_emergency_stop = True
                result = await dispatch_robot_action(
                    conn,
                    {"action_id": action_id, "source": "voice_rule", "params": {}},
                )
                self.assertEqual(result["status"], "accepted")

    def test_rk3588_bed_payload_uses_action_id_protocol(self):
        payload = build_bed_command_payload(
            {"hospice": {"robot_bed": {"device_id": "rk3588-bed-001"}}},
            "test-session",
            "manual_test",
            source="voice_rule",
            action_id="bed.feet.2",
            event_time="2026-09-02T12:00:00+08:00",
        )

        self.assertEqual(payload["type"], "bed.set")
        self.assertEqual(payload["device_id"], "rk3588-bed-001")
        self.assertEqual(payload["module"], "bed")
        self.assertEqual(payload["action_id"], "bed.feet.2")
        self.assertEqual(payload["params"], {})

    def test_rk3588_aroma_payload_uses_action_id_protocol(self):
        payload = build_aroma_command_payload(
            {"hospice": {"robot_aroma": {"device_id": "rk3588-eye-001"}}},
            "test-session",
            "manual_test",
            source="voice_rule",
            action_id="aroma.start",
            params={"type": "1", "duration_ms": 60000},
            event_time="2026-07-22T12:00:00+08:00",
        )

        self.assertEqual(payload["type"], "aroma.set")
        self.assertEqual(payload["module"], "aroma")
        self.assertEqual(payload["action_id"], "aroma.start")
        self.assertEqual(payload["params"], {"type": "1", "duration_ms": 60000})

    def test_rk3588_eye_payload_uses_action_id_protocol(self):
        payload = build_eye_command_payload(
            {"hospice": {"robot_eye": {"device_id": "rk3588-eye-001"}}},
            "test-session",
            "manual_test",
            "comfort",
            source="voice_rule",
            action_id="eye.gentle",
            module="eye",
            origin_action_id="arm.comfort",
            event_time="2026-06-23T15:59:32",
        )

        self.assertEqual(payload["action_id"], "eye.gentle")
        self.assertEqual(payload["origin_action_id"], "arm.comfort")
        self.assertEqual(payload["event_time"], "2026-06-23T15:59:32")
        self.assertNotIn("eye_expression", payload)

    def test_base_slamware_payload_matches_official_motion_schema(self):
        config = dict(BASE_SLAMWARE_DEFAULT_CONFIG)

        move_payload = _build_move_by_payload(config, "前进", {"distance_m": 0.2, "speed": 0.2})
        self.assertEqual(move_payload["action_name"], "slamtec.agent.actions.MoveByAction")
        self.assertEqual(move_payload["options"]["direction"], 0)
        self.assertEqual(move_payload["options"]["duration"], 1000)

        rotate_payload = _build_rotate_payload(config, "右转", {"angle": 30})
        self.assertEqual(rotate_payload["action_name"], "slamtec.agent.actions.RotateAction")
        self.assertAlmostEqual(rotate_payload["options"]["angle"], -0.5235987755982988)
        small_rotate_payload = _build_rotate_payload(config, "左转", {"angle": 5})
        self.assertEqual(small_rotate_payload["action_name"], "slamtec.agent.actions.RotateAction")
        self.assertAlmostEqual(small_rotate_payload["options"]["angle"], 0.08726646259971647)

        home_payload = _build_go_home_payload(config, multi_floor_enabled=True)
        self.assertEqual(home_payload["action_name"], "slamtec.agent.actions.GoHomeAction")
        self.assertEqual(home_payload["options"]["gohome_options"]["flags"], "dock")

    def test_base_slamware_poi_match_ignores_asr_trailing_punctuation(self):
        poi = {
            "id": "a6784945-6c94-4dec-8890-ef90d348f24b",
            "metadata": {"display_name": "一号测试点位"},
            "pose": {"x": -3.03, "y": 0.2, "yaw": 2.7},
        }

        self.assertTrue(_poi_name_matches(poi, "一号测试点位。"))
        self.assertTrue(_poi_name_matches(poi, " 一号测试点位 "))
        self.assertFalse(_poi_name_matches(poi, "二号测试点位。"))


if __name__ == "__main__":
    unittest.main()
