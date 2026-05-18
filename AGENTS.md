# AGENTS.md

本文件是给 Codex 和其他代码agents使用的仓库工作说明。

## 项目结构

- `main/xiaozhi-server/`：核心 Python AI 语音服务，负责 ESP32 设备的 WebSocket 通信、OTA/HTTP 辅助接口、AI Provider 模块、插件、配置加载和运行时数据。
- `main/xiaozhi-server/apps-src/patient/` 和 `main/xiaozhi-server/apps-src/family/`：Vite + React 网页应用。
- `mobile/`：Capacitor/移动端壳工程及相关应用代码。
- `voiceprint-api/`：声纹识别辅助 Python 服务/模块。
- `docs/`、`config/`、`data/`、`logs/` 和 `tmp/`：文档、配置、运行时数据、日志和临时输出。
- `main/manager-api/` ，`main/manager-web/` 和 `main/manager-mobile/`：当前不是默认工作范围，除非用户明确要求，否则不要分析或修改。

## 工作规则

- 保持改动范围聚焦在用户请求的组件内。本仓库是多服务仓库，修复某个问题时不要顺手重构无关服务。
- 除非任务明确要求，不要覆盖或删除 `data/`、`logs/`、`tmp/` 或生成构建目录下的用户文件/运行时文件。
- 将 API Key、Provider 凭据、`.env` 文件和 YAML 配置中的密钥视为敏感信息。不要在回复、测试或提交中打印或复制这些密钥。
- 保留现有编码和本地化文本。部分文件包含中文，在某些终端里可能显示异常；不要做大规模重新编码或无关格式化。
- 修改配置相关代码前，先确认该值来自本地 YAML、`manager-api`、环境变量，还是生成的运行时数据。
- 修改 Python Provider/插件时，遵循 `main/xiaozhi-server/core/providers/` 下现有的 Provider 模式，以及 `main/xiaozhi-server/plugins_func/` 下现有的插件模式。


## 常用命令

除非特别说明，从对应子目录运行命令。

### Python 服务

```powershell
cd main\xiaozhi-server
激活conda虚拟环境
conda activate xiaozhi-esp32-server
python app.py
```

### React 患者端/家属端应用

```powershell
cd main\xiaozhi-server\apps-src\patient
npm install
npm run build

cd ..\family
npm install
npm run build
```

## 验证要求

- 选择能覆盖本次行为改动的最小验证闭环。


## Git 规范

- 进行较大改动前后都检查 `git status --short`。
- 不要回滚用户改动或无关的未跟踪文件。
- 总结时说明改动路径、运行过的验证，以及剩余风险。
