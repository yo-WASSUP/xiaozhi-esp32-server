# 普通聊天症状知识检索

81 条原始问答保留在 symptom_qa.json。普通聊天不再直接播报匹配答案。
本地 BGE-small-zh-v1.5 量化 ONNX 模型检索最多 3 条完整原文，参考正文上限
1800 字符，附加到当前 LLM 请求；不写入历史，不新增聊天模型调用。
原有流式 TTS 保留。两三句是表达目标，适用条件、用药限制和求助条件优先。

部署：安装 requirements.txt，然后运行 `python scripts/setup_symptom_model.py`。
模型来源：https://huggingface.co/Xenova/bge-small-zh-v1.5
启动 `python app.py --config hospice` 时加载模型并建立索引，聊天中不下载模型。
启用功能但缺失模型时启动失败，避免无声绕过知识库。修改 JSON 后重启重建索引。
`hospice.symptom_qa.enabled: false` 关闭检索。旧 `min_score` 是文字匹配阈值，
已不用于语义检索；当前语义阈值为 0.55，须结合真实问句回归校准。

显式追问仅引用紧邻上一条用户消息，避免跨话题携带陈旧症状。
否定的标准症状名在检索查询中去除，原始用户消息始终完整交给聊天模型。
复合描述按分句保留候选。检索相似度不能用作医学判断或诊断置信度。
紧急求助条目会优先补入同症状参考，日志中的 0 分表示规则补入。

验证：`python -m unittest discover -s test -p "test_symptom*.py" -v`。
日志分别记录检索毫秒数、参考字符数、来源编号及 LLM 首包耗时。
检索耗时不包含 ASR、聊天生成、TTS 或网络；端到端首句延迟需设备实测。
现有资料尚未经本次临床审校，提示约束不能替代临床内容审查。
