# AGENTS.md

本文件是给 Codex 使用的仓库工作说明。

## 项目结构

- `main/xiaozhi-server/`：核心 Python AI 语音服务，负责 ESP32 设备的 WebSocket 通信、OTA/HTTP 辅助接口、AI Provider 模块、插件、配置加载和运行时数据。
- `main/xiaozhi-server/apps-src/patient/` 和 `main/xiaozhi-server/apps-src/family/`：Vite + React 网页应用。
- `mobile/`：Capacitor/移动端壳工程及相关应用代码。
- `voiceprint-api/`：声纹识别辅助 Python 服务/模块。
- `docs/`、`config/`、`data/`、`logs/` 和 `tmp/`：文档、配置、运行时数据、日志和临时输出。
- `main/manager-api/` ，`main/manager-web/` 和 `main/manager-mobile/`：当前不是默认工作范围，除非用户明确要求，否则不要分析或修改。

## 工作规则

- 保持改动范围聚焦在用户请求的组件内。
- 除非任务明确要求，不要覆盖或删除 `data/`、`logs/`、`tmp/` 或生成构建目录下的用户文件/运行时文件。


## 常用命令

除非特别说明，从对应子目录运行命令。

### Python 服务

```powershell
cd main\xiaozhi-server
激活conda虚拟环境
conda activate xiaozhi-esp32-server
python app.py
python app.py --config hospice
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

## 回复要求
 
- 每次回复都要叫我主人
- 不能说不是... 而是...句型， 或者类似的表达，直接说重点。