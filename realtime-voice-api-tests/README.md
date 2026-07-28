# 全双工实时语音 API 本地测试

这个目录提供一个统一网页控制台，以及三个相互独立的命令行测试脚本：

- `gpt-realtime-2.1`：OpenAI `gpt-realtime-2.1`
- `qwen3.5-omni-realtime`：阿里云百炼 `qwen3.5-omni-plus-realtime`
- `doubao-s2s-o`：火山引擎端到端实时语音模型 O

三个脚本都会持续上传麦克风 PCM、流式播放模型音频、输出转写和关键事件，并在检测到插话时清空本地播放缓冲区。按 `Ctrl+C` 结束。

## 网页控制台

三家凭据继续填写在各自子目录的 `.env`。启动本地服务：

```powershell
python .\web\server.py
```

浏览器打开：

```text
http://127.0.0.1:8765
```

网页可以切换接口、开始或结束通话、关闭麦克风，并实时显示双方转写、模型首包延迟、端到端首音、完整响应时间、说话时长和播放缓冲。

## 安装

在本目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果 Windows 找不到输入或输出设备，先在系统隐私设置中允许终端访问麦克风，并确认默认扬声器可用。

## 命令行运行

进入目标子目录，将 `.env.example` 复制为 `.env`，填写控制台申请的凭据，然后从本目录运行：

```powershell
python .\gpt-realtime-2.1\app.py
python .\qwen3.5-omni-realtime\app.py
python .\doubao-s2s-o\app.py
```

为避免回声触发误打断，测试时建议佩戴耳机。三家接口都会产生 API 费用，请在对应平台查看实时价格与配额。
