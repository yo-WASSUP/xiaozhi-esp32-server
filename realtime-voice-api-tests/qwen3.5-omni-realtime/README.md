# Qwen3.5 Omni Realtime

1. 在阿里云百炼控制台取得 API Key 和业务空间 ID。
2. 复制环境变量文件，填写 `DASHSCOPE_API_KEY`，并配置业务空间 ID 或完整实时地址：

```powershell
Copy-Item .\qwen3.5-omni-realtime\.env.example .\qwen3.5-omni-realtime\.env
```

3. 从上级 `realtime-voice-api-tests` 目录运行：

```powershell
python .\qwen3.5-omni-realtime\app.py
```

脚本上传 16 kHz PCM，播放 24 kHz PCM，默认启用响应更快的 Server VAD、输入转写和插话取消。可通过 `QWEN_VAD_*` 环境变量调整判停参数。官方资料：

- 推荐方式：填写 `QWEN_WORKSPACE_ID`，使用业务空间专属域名。
- 兼容方式：已有 DashScope Key 可设置 `QWEN_REALTIME_URL=wss://dashscope.aliyuncs.com/api-ws/v1/realtime`。

- https://help.aliyun.com/zh/model-studio/realtime
