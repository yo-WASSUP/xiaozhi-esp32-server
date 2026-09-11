import unittest

from core.dignity import symptom_retrieval as retrieval
from core.utils.dialogue import Message


class SymptomRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = retrieval.warmup()

    def test_colloquial_symptoms(self):
        for query, symptom in [("吃两口就不想吃了", "厌食"), ("晚上总是睡不着", "失眠"),
                               ("我喘不过气了", "呼吸困难")]:
            with self.subTest(query=query):
                self.assertEqual(self.index.retrieve(query)[0][0].symptom, symptom)

    def test_followup_uses_previous_user_turn(self):
        result = self.index.retrieve("那怎么跟护士说", [Message("user", "疼痛怎么办")])
        self.assertIn("描述疼痛", result[0][0].question)

    def test_unrelated_and_ambiguous(self):
        for query in ["今天天气怎么样", "讲个笑话", "我今天心情不错", "什么情况下需要立即求助"]:
            self.assertEqual(self.index.retrieve(query), [], query)

    def test_negation_and_topic_change(self):
        self.assertEqual(self.index.retrieve("我没有疼痛，只是睡不着")[0][0].symptom, "失眠")
        result = self.index.retrieve("晚上总是睡不着", [Message("user", "疼痛怎么办")])
        self.assertEqual(result[0][0].symptom, "失眠")
        self.assertEqual(self.index.retrieve("那明天天气呢", [Message("user", "今天天气怎么样")]), [])

    def test_multiple_symptoms(self):
        symptoms = {entry.symptom for entry, _ in self.index.retrieve("我便秘还睡不着")}
        self.assertTrue({"便秘", "失眠"}.issubset(symptoms))

    def test_chat_calls_one_model_with_request_only_references(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from core.connection_parts.chat import ChatMixin
        from core.utils.dialogue import Dialogue
        for intent_type in ("intent_llm", "function_call"):
            with self.subTest(intent_type=intent_type):
                conn = SimpleNamespace(
                    dialogue=Dialogue(), config={"hospice": {"symptom_qa": {}}},
                    logger=MagicMock(), tts=MagicMock(), memory=None,
                    llm=MagicMock(), intent_type=intent_type,
                    func_handler=MagicMock(), session_id="test", client_abort=False,
                )
                conn.llm.response.return_value = iter(())
                conn.llm.response_with_functions.return_value = iter(())
                conn.func_handler.get_functions.return_value = []
                self.assertTrue(ChatMixin.chat(conn, "疼痛怎么办"))
                method = conn.llm.response_with_functions if intent_type == "function_call" else conn.llm.response
                method.assert_called_once()
                self.assertIn("本轮症状知识参考", method.call_args.args[1][0]["content"])
                self.assertEqual(len(conn.dialogue.dialogue), 1)
                self.assertEqual(conn.dialogue.dialogue[0].content, "疼痛怎么办")

    def test_request_only_and_whole_source_answers(self):
        dialogue = [{"role": "system", "content": "原提示"}, {"role": "user", "content": "疼痛怎么办"}]
        original = [dict(m) for m in dialogue]
        result, sources, size = retrieval.add_references(dialogue, "疼痛怎么办")
        self.assertEqual(dialogue, original)
        self.assertTrue(sources)
        self.assertLessEqual(size, 1800)
        for entry, _ in self.index.retrieve("疼痛怎么办"):
            self.assertIn(entry.answer, result[0]["content"])
        second, sources, size = retrieval.add_references(dialogue, "讲个笑话")
        self.assertEqual(second, original)
        self.assertFalse(sources)

    def test_disabled_config(self):
        self.assertFalse(retrieval.enabled({}))
        self.assertFalse(retrieval.enabled({"hospice": {"symptom_qa": False}}))
        self.assertFalse(retrieval.enabled({"hospice": {"symptom_qa": {"enabled": False}}}))
        self.assertTrue(retrieval.enabled({"hospice": {"symptom_qa": {}}}))
