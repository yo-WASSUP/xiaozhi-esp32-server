# 豆包 S2S-O

1. 在火山引擎豆包语音新版控制台开通端到端实时语音服务，并在“API Key 管理”取得 API Key。
2. 复制环境变量文件并填写 `DOUBAO_API_KEY`：

```powershell
Copy-Item .\doubao-s2s-o\.env.example .\doubao-s2s-o\.env
```

3. 从上级 `realtime-voice-api-tests` 目录运行：

```powershell
python .\doubao-s2s-o\app.py
```

脚本实现火山引擎 V3 二进制 WebSocket 协议，上传 16 kHz PCM16，播放 24 kHz PCM16，并在 ASR 检测到插话时发送 `ClientInterrupt`。默认模型版本 `1.2.1.1` 对应 O，默认音色为 `zh_female_vv_jupiter_bigtts`，输出格式为 `pcm_s16le`，判停时间为 800 ms。

官方资料：

- https://www.volcengine.com/docs/6561/1594356
- https://www.volcengine.com/product/realtime-voice-model
