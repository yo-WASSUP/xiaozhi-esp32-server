# GPT Realtime 2.1

1. 复制环境变量文件并填写 API Key：

```powershell
Copy-Item .\gpt-realtime-2.1\.env.example .\gpt-realtime-2.1\.env
```

2. 从上级 `realtime-voice-api-tests` 目录运行：

```powershell
python .\gpt-realtime-2.1\app.py
```

脚本使用 24 kHz、16 位、单声道 PCM，启用 Semantic VAD 和自动打断。官方资料：

- https://developers.openai.com/api/docs/models/gpt-realtime-2.1
- https://developers.openai.com/api/docs/guides/realtime-conversations

