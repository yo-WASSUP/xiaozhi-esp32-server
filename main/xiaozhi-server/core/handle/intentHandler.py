import json
import uuid
import asyncio
from core.utils.dialogue import Message
from core.providers.tts.dto.dto import ContentType
from core.handle.helloHandle import checkWakeupWords
from plugins_func.register import Action, ActionResponse
from core.handle.sendAudioHandle import send_stt_message
from core.utils.util import remove_punctuation_and_length
from core.providers.tts.dto.dto import TTSMessageDTO, SentenceType

TAG = __name__


async def handle_user_intent(conn, text):
    # 预处理输入文本，处理可能的JSON格式
    try:
        if text.strip().startswith('{') and text.strip().endswith('}'):
            parsed_data = json.loads(text)
            if isinstance(parsed_data, dict) and "content" in parsed_data:
                text = parsed_data["content"]  # 提取content用于意图分析
                conn.current_speaker = parsed_data.get("speaker")  # 保留说话人信息
    except (json.JSONDecodeError, TypeError):
        pass

    # 检查是否有明确的退出命令
    _, filtered_text = remove_punctuation_and_length(text)
    if await check_direct_exit(conn, filtered_text):
        return True

    # 检查是否是唤醒词
    if await checkWakeupWords(conn, filtered_text):
        return True

    if await handle_dignity_voice_switch(conn, text):
        return True

    # 安宁疗护患者端：本地动作指令直接下发给前端执行，不进入普通聊天。
    hospice_config = conn.config.get("hospice", {}) or {}
    if hospice_config and hospice_config.get("enable_patient_voice_actions", True):
        try:
            from core.api.hospice.patient_actions import detect_patient_action
            patient_action = detect_patient_action(text)
            if patient_action:
                action = patient_action.get("action")
                if action == "accept_call":
                    conn.hospice_call_active = True
                    conn.logger.bind(tag=TAG).info("安宁疗护患者端进入通话指令模式")
                elif action in ("reject_call", "hangup_call"):
                    conn.hospice_call_active = False
                    conn.logger.bind(tag=TAG).info("安宁疗护患者端退出通话指令模式")
                await send_stt_message(conn, text)
                await conn.websocket.send(json.dumps(patient_action, ensure_ascii=False))
                conn.logger.bind(tag=TAG).info(
                    f"安宁疗护患者端动作: {action}"
                )
                return True
        except Exception as e:
            conn.logger.bind(tag=TAG).warning(f"患者端动作指令处理失败: {e}")

    if getattr(conn, "hospice_call_active", False):
        conn.logger.bind(tag=TAG).info("通话中语音未命中患者端动作，已忽略普通对话处理")
        return True

    if not getattr(conn, "dignity_active", False):
        if await handle_hospice_symptom_qa(conn, text):
            return True

    if hospice_config and hospice_config.get("enable_robot_voice_actions", True):
        try:
            from core.robot_actions import classify_robot_action, dispatch_robot_action

            robot_action = await classify_robot_action(conn, text)
            if robot_action:
                await send_stt_message(conn, text)
                await dispatch_robot_action(conn, robot_action, source_event="voice_action")
                return True
        except Exception as e:
            conn.logger.bind(tag=TAG).warning(f"机器人语音动作处理失败: {e}")

    try:
        from core.dignity.runtime import handle_dignity_turn_if_active

        if await handle_dignity_turn_if_active(conn, text):
            return True
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"尊严疗法模式处理失败: {e}")

    if await handle_hospice_patient_sleep(conn, text, filtered_text):
        return True

    if conn.intent_type == "function_call":
        # 使用支持function calling的聊天方法,不再进行意图分析
        return False
    # 使用LLM进行意图分析
    intent_result = await analyze_intent_with_llm(conn, text)
    if not intent_result:
        return False
    # 会话开始时生成sentence_id
    conn.sentence_id = str(uuid.uuid4().hex)
    # 处理各种意图
    return await process_intent_result(conn, intent_result, text)


async def _send_patient_voice_action(conn, action, text, **extra):
    await conn.websocket.send(
        json.dumps(
            {
                "type": "client_action",
                "action": action,
                "text": text,
                **extra,
            },
            ensure_ascii=False,
        )
    )


async def handle_dignity_voice_switch(conn, original_text):
    try:
        from core.dignity.runtime import start_dignity_mode, stop_dignity_mode
        from core.dignity.voice_commands import detect_dignity_voice_command

        command = detect_dignity_voice_command(original_text, conn.config)
        if not command:
            return False

        await send_stt_message(conn, original_text)
        payload = {
            "source": "voice_command",
            "auto_voice_mode": True,
            "trigger_text": original_text,
            "matched_command": command.get("matched_command", ""),
        }
        device_id = getattr(conn, "device_id", None) or (
            getattr(conn, "headers", None) or {}
        ).get("device-id")
        if device_id:
            payload["patient_id"] = device_id

        if command.get("action") == "start":
            conn.logger.bind(tag=TAG).info("语音指令开启尊严疗法模式")
            await start_dignity_mode(conn, payload)
        else:
            conn.logger.bind(tag=TAG).info("语音指令关闭尊严疗法模式")
            await stop_dignity_mode(conn, payload)
        return True
    except Exception as e:
        conn.logger.bind(tag=TAG).warning(f"尊严疗法语音开关处理失败: {e}")
        return False


async def handle_hospice_patient_sleep(conn, original_text, filtered_text):
    hospice_config = conn.config.get("hospice", {}) or {}
    if not hospice_config or not hospice_config.get("enable_patient_wakeup", True):
        return False

    sleep_commands = []
    for item in hospice_config.get("patient_sleep_commands") or []:
        _, value = remove_punctuation_and_length(str(item or ""))
        if value:
            sleep_commands.append(value)
    sleep_commands = sorted(set(sleep_commands), key=len, reverse=True)
    text = filtered_text or ""

    if any(command and command in text for command in sleep_commands):
        conn.logger.bind(tag=TAG).info("患者端普通聊天进入待机")
        await send_stt_message(conn, original_text)
        await _send_patient_voice_action(conn, "patient_voice_sleep", original_text)
        return True

    return False


async def check_direct_exit(conn, text):
    """检查是否有明确的退出命令"""
    _, text = remove_punctuation_and_length(text)
    cmd_exit = conn.cmd_exit
    for cmd in cmd_exit:
        if text == cmd:
            conn.logger.bind(tag=TAG).info(f"识别到明确的退出命令: {text}")
            await send_stt_message(conn, text)
            await conn.close()
            return True
    return False


async def analyze_intent_with_llm(conn, text):
    """使用LLM分析用户意图"""
    if not hasattr(conn, "intent") or not conn.intent:
        conn.logger.bind(tag=TAG).warning("意图识别服务未初始化")
        return None

    # 对话历史记录
    dialogue = conn.dialogue
    try:
        intent_result = await conn.intent.detect_intent(conn, dialogue.dialogue, text)
        return intent_result
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"意图识别失败: {str(e)}")

    return None


async def handle_hospice_symptom_qa(conn, text):
    hospice_config = conn.config.get("hospice", {}) or {}
    if not hospice_config:
        return False

    qa_config = hospice_config.get("symptom_qa", {})
    if qa_config is False or (
        isinstance(qa_config, dict) and qa_config.get("enabled", True) is False
    ):
        return False

    try:
        from core.dignity.symptom_qa import DEFAULT_MIN_SCORE, match_symptom_question

        min_score = (
            float(qa_config.get("min_score", DEFAULT_MIN_SCORE))
            if isinstance(qa_config, dict)
            else DEFAULT_MIN_SCORE
        )
        match = match_symptom_question(text, min_score=min_score)
    except Exception as e:
        conn.logger.bind(tag=TAG).warning(f"症状问答库匹配失败，继续普通聊天: {e}")
        return False

    if match is None:
        return False

    conn.sentence_id = str(uuid.uuid4().hex)
    conn.client_abort = False
    await send_stt_message(conn, text)
    conn.dialogue.put(Message(role="user", content=text))
    speak_txt(conn, match.entry.answer)
    conn.logger.bind(tag=TAG).info(
        "症状问答库命中: "
        f"symptom={match.entry.symptom}, question={match.entry.question}, "
        f"source_row={match.entry.source_row}, match_type={match.match_type}, "
        f"score={match.score:.3f}"
    )
    return True


async def process_intent_result(conn, intent_result, original_text):
    """处理意图识别结果"""
    try:
        # 尝试将结果解析为JSON
        intent_data = json.loads(intent_result)

        # 检查是否有function_call
        if "function_call" in intent_data:
            # 直接从意图识别获取了function_call
            conn.logger.bind(tag=TAG).debug(
                f"检测到function_call格式的意图结果: {intent_data['function_call']['name']}"
            )
            function_name = intent_data["function_call"]["name"]
            if function_name == "continue_chat":
                return False

            if function_name == "result_for_context":
                await send_stt_message(conn, original_text)
                conn.client_abort = False
                
                def process_context_result():
                    conn.dialogue.put(Message(role="user", content=original_text))
                    
                    from core.utils.current_time import get_current_time_info

                    current_time, today_date, today_weekday, lunar_date = get_current_time_info()
                    
                    # 构建带上下文的基础提示
                    context_prompt = f"""当前时间：{current_time}
                                        今天日期：{today_date} ({today_weekday})
                                        今天农历：{lunar_date}

                                        请根据以上信息回答用户的问题：{original_text}"""
                    
                    response = conn.intent.replyResult(context_prompt, original_text)
                    speak_txt(conn, response)
                
                conn.executor.submit(process_context_result)
                return True

            function_args = {}
            if "arguments" in intent_data["function_call"]:
                function_args = intent_data["function_call"]["arguments"]
                if function_args is None:
                    function_args = {}
            # 确保参数是字符串格式的JSON
            if isinstance(function_args, dict):
                function_args = json.dumps(function_args)

            function_call_data = {
                "name": function_name,
                "id": str(uuid.uuid4().hex),
                "arguments": function_args,
            }

            await send_stt_message(conn, original_text)
            conn.client_abort = False

            # 使用executor执行函数调用和结果处理
            def process_function_call():
                conn.dialogue.put(Message(role="user", content=original_text))

                # 使用统一工具处理器处理所有工具调用
                try:
                    result = asyncio.run_coroutine_threadsafe(
                        conn.func_handler.handle_llm_function_call(
                            conn, function_call_data
                        ),
                        conn.loop,
                    ).result()
                except Exception as e:
                    conn.logger.bind(tag=TAG).error(f"工具调用失败: {e}")
                    result = ActionResponse(
                        action=Action.ERROR, result=str(e), response=str(e)
                    )

                if result:
                    if result.action == Action.RESPONSE:  # 直接回复前端
                        text = result.response
                        if text is not None:
                            speak_txt(conn, text)
                    elif result.action == Action.REQLLM:  # 调用函数后再请求llm生成回复
                        text = result.result
                        conn.dialogue.put(Message(role="tool", content=text))
                        llm_result = conn.intent.replyResult(text, original_text)
                        if llm_result is None:
                            llm_result = text
                        speak_txt(conn, llm_result)
                    elif (
                        result.action == Action.NOTFOUND
                        or result.action == Action.ERROR
                    ):
                        text = result.result
                        if text is not None:
                            speak_txt(conn, text)
                    elif function_name != "play_music":
                        # For backward compatibility with original code
                        # 获取当前最新的文本索引
                        text = result.response
                        if text is None:
                            text = result.result
                        if text is not None:
                            speak_txt(conn, text)

            # 将函数执行放在线程池中
            conn.executor.submit(process_function_call)
            return True
        return False
    except json.JSONDecodeError as e:
        conn.logger.bind(tag=TAG).error(f"处理意图结果时出错: {e}")
        return False


def speak_txt(conn, text, record_dialogue=True):
    # 记录文本
    conn.tts_MessageText = text

    conn.tts.tts_text_queue.put(
        TTSMessageDTO(
            sentence_id=conn.sentence_id,
            sentence_type=SentenceType.FIRST,
            content_type=ContentType.ACTION,
        )
    )
    conn.tts.tts_one_sentence(conn, ContentType.TEXT, content_detail=text)
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(
            sentence_id=conn.sentence_id,
            sentence_type=SentenceType.LAST,
            content_type=ContentType.ACTION,
        )
    )
    if record_dialogue:
        conn.dialogue.put(Message(role="assistant", content=text))
