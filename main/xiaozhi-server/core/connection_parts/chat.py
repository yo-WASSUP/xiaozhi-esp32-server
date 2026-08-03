import asyncio
import json
import time
import uuid

from core.providers.tts.dto.dto import ContentType, TTSMessageDTO, SentenceType
from core.handle.sendAudioHandle import send_llm_message
from core.utils import textUtils
from core.utils.dialogue import Message
from core.utils.util import extract_json_from_string, get_system_error_response
from plugins_func.register import Action


TAG = __name__

EMOTION_TAG_PREFIX = "<!--emotion:"
EMOTION_TAG_END = "-->"


def _filter_stream_emotion_tag(content, pending=""):
    """Remove hospice emotion tags before streaming text to TTS."""
    if not content:
        return "", pending

    combined = pending + content
    output = []
    index = 0

    while index < len(combined):
        tag_start = combined.find(EMOTION_TAG_PREFIX, index)
        if tag_start == -1:
            tail = combined[index:]
            keep = 0
            max_keep = min(len(tail), len(EMOTION_TAG_PREFIX) - 1)
            for size in range(max_keep, 0, -1):
                if tail.endswith(EMOTION_TAG_PREFIX[:size]):
                    keep = size
                    break
            if keep:
                output.append(tail[:-keep])
                return "".join(output), tail[-keep:]
            output.append(tail)
            return "".join(output), ""

        output.append(combined[index:tag_start])
        tag_end = combined.find(EMOTION_TAG_END, tag_start + len(EMOTION_TAG_PREFIX))
        if tag_end == -1:
            return "".join(output), combined[tag_start:]
        index = tag_end + len(EMOTION_TAG_END)

    return "".join(output), ""


class ChatMixin:
    def chat(self, query, depth=0):
        if query is not None:
            self.logger.bind(tag=TAG).info(f"大模型收到用户消息: {query}")

        # 为最顶层时新建会话ID和发送FIRST请求
        if depth == 0:
            self.sentence_id = str(uuid.uuid4().hex)
            self.dialogue.put(Message(role="user", content=query))
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=self.sentence_id,
                    sentence_type=SentenceType.FIRST,
                    content_type=ContentType.ACTION,
                )
            )

        # 设置最大递归深度，避免无限循环，可根据实际需求调整
        MAX_DEPTH = 5
        force_final_answer = False  # 标记是否强制最终回答

        if depth >= MAX_DEPTH:
            self.logger.bind(tag=TAG).debug(
                f"已达到最大工具调用深度 {MAX_DEPTH}，将强制基于现有信息回答"
            )
            force_final_answer = True
            # 添加系统指令，要求 LLM 基于现有信息回答
            self.dialogue.put(
                Message(
                    role="user",
                    content="[系统提示] 已达到最大工具调用次数限制，请你基于目前已经获取的所有信息，直接给出最终答案。不要再尝试调用任何工具。",
                )
            )

        # Define intent functions
        functions = None
        # 达到最大深度时，禁用工具调用，强制 LLM 直接回答
        if (
            self.intent_type == "function_call"
            and hasattr(self, "func_handler")
            and not force_final_answer
        ):
            functions = self.func_handler.get_functions()
        response_message = []
        final_display_text = ""

        try:
            # LLM 调用性能日志（普通聊天）
            model_info = getattr(self.llm, "model_name", self.llm.__class__.__name__)
            llm_total_start = time.time()
            self.logger.bind(tag=TAG).debug(f"开始LLM对话调用, 模型: {model_info}")
            # 使用带记忆的对话
            memory_str = None
            if self.memory is not None:
                future = asyncio.run_coroutine_threadsafe(
                    self.memory.query_memory(query), self.loop
                )
                memory_str = future.result()

            if self.intent_type == "function_call" and functions is not None:
                # 使用支持functions的streaming接口
                dialogue_data = self.dialogue.get_llm_dialogue_with_memory(
                    memory_str, self.config.get("voiceprint", {})
                )
                # 计算输入文字长度
                dialogue_chars = sum(
                    len(str(msg.get("content", ""))) for msg in dialogue_data
                )
                functions_chars = len(json.dumps(functions, ensure_ascii=False))
                self.logger.bind(tag=TAG).info(
                    f"【性能】LLM输入 - 对话: {dialogue_chars}字, 函数定义: {functions_chars}字, "
                    f"函数数量: {len(functions)}, 总计: {dialogue_chars + functions_chars}字"
                )
                llm_responses = self.llm.response_with_functions(
                    self.session_id,
                    dialogue_data,
                    functions=functions,
                )
            else:
                dialogue_data = self.dialogue.get_llm_dialogue_with_memory(
                    memory_str, self.config.get("voiceprint", {})
                )
                dialogue_chars = sum(
                    len(str(msg.get("content", ""))) for msg in dialogue_data
                )
                self.logger.bind(tag=TAG).info(
                    f"【性能】LLM输入 - 对话: {dialogue_chars}字"
                )
                llm_responses = self.llm.response(
                    self.session_id,
                    dialogue_data,
                )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"LLM 处理出错 {query}: {e}")
            return None

        # 处理流式响应
        tool_call_flag = False
        # 支持多个并行工具调用 - 使用列表存储
        tool_calls_list = []  # 格式: [{"id": "", "name": "", "arguments": ""}]
        content_arguments = ""
        emotion_tag_pending = ""
        self.client_abort = False
        emotion_flag = True
        first_token_ms = None
        self.llm_first_token_time = None  # 用于TTS延迟计算
        try:
            for response in llm_responses:
                if first_token_ms is None:
                    first_token_ms = (time.time() - llm_total_start) * 1000
                    self.llm_first_token_time = time.time()  # 记录LLM首包绝对时间
                if self.client_abort:
                    break
                if self.intent_type == "function_call" and functions is not None:
                    content, tools_call = response
                    if "content" in response:
                        content = response["content"]
                        tools_call = None
                    if content is not None and len(content) > 0:
                        content_arguments += content

                    if not tool_call_flag and content_arguments.startswith("<tool_call>"):
                        tool_call_flag = True

                    if tools_call is not None and len(tools_call) > 0:
                        tool_call_flag = True
                        self._merge_tool_calls(tool_calls_list, tools_call)
                else:
                    content = response

                # 在llm回复中获取情绪表情，一轮对话只在开头获取一次
                if emotion_flag and content is not None and content.strip():
                    asyncio.run_coroutine_threadsafe(
                        textUtils.get_emotion(self, content),
                        self.loop,
                    )
                    emotion_flag = False

                if content is not None and len(content) > 0:
                    if not tool_call_flag:
                        tts_content, emotion_tag_pending = _filter_stream_emotion_tag(
                            content, emotion_tag_pending
                        )
                        response_message.append(content)
                        if tts_content:
                            self.tts.tts_text_queue.put(
                                TTSMessageDTO(
                                    sentence_id=self.sentence_id,
                                    sentence_type=SentenceType.MIDDLE,
                                    content_type=ContentType.TEXT,
                                    content_detail=tts_content,
                                )
                            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"LLM stream processing error: {e}")
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=self.sentence_id,
                    sentence_type=SentenceType.MIDDLE,
                    content_type=ContentType.TEXT,
                    content_detail=get_system_error_response(self.config),
                )
            )
            if depth == 0:
                self.tts.tts_text_queue.put(
                    TTSMessageDTO(
                        sentence_id=self.sentence_id,
                        sentence_type=SentenceType.LAST,
                        content_type=ContentType.ACTION,
                    )
                )
            return
        # 处理function call
        if tool_call_flag:
            bHasError = False
            # 处理基于文本的工具调用格式
            if len(tool_calls_list) == 0 and content_arguments:
                a = extract_json_from_string(content_arguments)
                if a is not None:
                    try:
                        content_arguments_json = json.loads(a)
                        tool_calls_list.append(
                            {
                                "id": str(uuid.uuid4().hex),
                                "name": content_arguments_json["name"],
                                "arguments": json.dumps(
                                    content_arguments_json["arguments"],
                                    ensure_ascii=False,
                                ),
                            }
                        )
                    except Exception:
                        bHasError = True
                        response_message.append(a)
                else:
                    bHasError = True
                    response_message.append(content_arguments)
                if bHasError:
                    self.logger.bind(tag=TAG).error(
                        f"function call error: {content_arguments}"
                    )

            if not bHasError and len(tool_calls_list) > 0:
                # 如需要大模型先处理一轮，添加相关处理后的日志情况
                if len(response_message) > 0:
                    text_buff = "".join(response_message)
                    self.tts_MessageText = text_buff
                    self.dialogue.put(Message(role="assistant", content=text_buff))
                response_message.clear()

                self.logger.bind(tag=TAG).debug(
                    f"检测到 {len(tool_calls_list)} 个工具调用"
                )

                # 收集所有工具调用的 Future
                futures_with_data = []
                for tool_call_data in tool_calls_list:
                    self.logger.bind(tag=TAG).debug(
                        f"function_name={tool_call_data['name']}, function_id={tool_call_data['id']}, function_arguments={tool_call_data['arguments']}"
                    )

                    future = asyncio.run_coroutine_threadsafe(
                        self.func_handler.handle_llm_function_call(
                            self, tool_call_data
                        ),
                        self.loop,
                    )
                    futures_with_data.append((future, tool_call_data))

                # 等待协程结束（实际等待时长为最慢的那个）
                tool_results = []
                for future, tool_call_data in futures_with_data:
                    result = future.result()
                    tool_results.append((result, tool_call_data))

                # 统一处理所有工具调用结果
                if tool_results:
                    self._handle_function_result(tool_results, depth=depth)

        # 存储对话内容
        if len(response_message) > 0:
            text_buff = "".join(response_message)

            # ── 安宁疗护：情感解析 + 会话日志 ──
            try:
                from core.providers.emotion import parse_emotion

                clean_text, emotion_data = parse_emotion(text_buff)
                self.tts_MessageText = clean_text
                final_display_text = clean_text
                # 存入对话历史时去掉情感标签，避免标签累积
                self.dialogue.put(Message(role="assistant", content=clean_text))

                # 记录到会话日志（如果启用了 hospice 模块）
                hospice_config = self.config.get("hospice", {})
                if hospice_config.get("enable_logging", False):
                    from core.api.hospice.storage import get_session_logger

                    session_logger = get_session_logger(self.config)
                    device_id = self.device_id or "default"
                    # 记录用户消息
                    if query:
                        session_logger.log_conversation(
                            device_id, self.session_id, "patient", query
                        )
                    # 记录助手回复 + 情感
                    mood = emotion_data.get("mood") if emotion_data else None
                    intensity = emotion_data.get("intensity") if emotion_data else None
                    session_logger.log_conversation(
                        device_id,
                        self.session_id,
                        "assistant",
                        clean_text,
                        emotion_mood=mood,
                        emotion_intensity=intensity,
                    )
            except Exception as e:
                self.logger.bind(tag=TAG).debug(f"情感解析/会话日志记录跳过: {e}")
                self.tts_MessageText = text_buff
                final_display_text = text_buff
                self.dialogue.put(Message(role="assistant", content=text_buff))

        # LLM 调用总耗时日志
        if final_display_text:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    send_llm_message(self, final_display_text),
                    self.loop,
                )
                future.result(timeout=2)
            except Exception as e:
                self.logger.bind(tag=TAG).warning(
                    f"完整 LLM 文本发送失败: {e}"
                )

        llm_total_ms = (time.time() - llm_total_start) * 1000
        try:
            preview = (query or "")[:20]
        except Exception:
            preview = ""
        if first_token_ms is None:
            # 无流数据也记录总耗时
            first_token_ms = llm_total_ms
        self.logger.bind(tag=TAG).debug(
            f"【LLM聊天性能】模型: {model_info}, 首包: {first_token_ms:.2f}ms, 总耗时: {llm_total_ms:.2f}ms, 输入: '{preview}...'"
        )
        if depth == 0:
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=self.sentence_id,
                    sentence_type=SentenceType.LAST,
                    content_type=ContentType.ACTION,
                )
            )
            # 使用lambda延迟计算，只有在DEBUG级别时才执行get_llm_dialogue()
            self.logger.bind(tag=TAG).debug(
                lambda: json.dumps(
                    self.dialogue.get_llm_dialogue(), indent=4, ensure_ascii=False
                )
            )

        return True

    def _handle_function_result(self, tool_results, depth):
        need_llm_tools = []

        for result, tool_call_data in tool_results:
            # 通知客户端工具调用信息
            try:
                tool_info = {
                    "type": "tool_call",
                    "function": tool_call_data.get("name", ""),
                    "arguments": tool_call_data.get("arguments", "{}"),
                    "result": result.response or result.result or "",
                    "action": result.action.name if result.action else "",
                }
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send(json.dumps(tool_info, ensure_ascii=False)),
                    self.loop,
                )
            except Exception as e:
                self.logger.bind(tag=TAG).debug(f"发送工具调用信息失败: {e}")

            if result.action in [
                Action.RESPONSE,
                Action.NOTFOUND,
                Action.ERROR,
            ]:  # 直接回复前端
                text = result.response if result.response else result.result
                self.tts.tts_one_sentence(self, ContentType.TEXT, content_detail=text)
                self.dialogue.put(Message(role="assistant", content=text))
            elif result.action == Action.REQLLM:
                # 收集需要 LLM 处理的工具
                need_llm_tools.append((result, tool_call_data))
            else:
                pass

        if need_llm_tools:
            all_tool_calls = [
                {
                    "id": tool_call_data["id"],
                    "function": {
                        "arguments": (
                            "{}"
                            if tool_call_data["arguments"] == ""
                            else tool_call_data["arguments"]
                        ),
                        "name": tool_call_data["name"],
                    },
                    "type": "function",
                    "index": idx,
                }
                for idx, (_, tool_call_data) in enumerate(need_llm_tools)
            ]
            self.dialogue.put(Message(role="assistant", tool_calls=all_tool_calls))

            for result, tool_call_data in need_llm_tools:
                text = result.result
                if text is not None and len(text) > 0:
                    self.dialogue.put(
                        Message(
                            role="tool",
                            tool_call_id=(
                                str(uuid.uuid4())
                                if tool_call_data["id"] is None
                                else tool_call_data["id"]
                            ),
                            content=text,
                        )
                    )

            self.chat(None, depth=depth + 1)

    def chat_and_close(self, text):
        """Chat with the user and then close the connection"""
        try:
            self.chat(text)
            self.close_after_chat = True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Chat and close error: {str(e)}")

    def _merge_tool_calls(self, tool_calls_list, tools_call):
        """合并工具调用列表

        Args:
            tool_calls_list: 已收集的工具调用列表
            tools_call: 新的工具调用
        """
        for tool_call in tools_call:
            tool_index = getattr(tool_call, "index", None)
            if tool_index is None:
                if tool_call.function.name:
                    # 有 function_name，说明是新的工具调用
                    tool_index = len(tool_calls_list)
                else:
                    tool_index = len(tool_calls_list) - 1 if tool_calls_list else 0

            # 确保列表有足够的位置
            if tool_index >= len(tool_calls_list):
                tool_calls_list.append({"id": "", "name": "", "arguments": ""})

            # 更新工具调用信息
            if tool_call.id:
                tool_calls_list[tool_index]["id"] = tool_call.id
            if tool_call.function.name:
                tool_calls_list[tool_index]["name"] = tool_call.function.name
            if tool_call.function.arguments:
                tool_calls_list[tool_index]["arguments"] += tool_call.function.arguments
