# 安宁疗护前端：开发与打包手册

覆盖 **家属端（family）** 和 **患者端（patient）** 两个应用，从"改代码"到"出 APK"的全流程。

---

## 1. 项目结构

```
main/xiaozhi-server/
├── apps-src/                  ← 前端源码（Vite + React）
│   ├── family/
│   │   ├── src/               ← 组件 / 屏幕 / hooks / utils
│   │   ├── public/            ← manifest.json / sw.js（构建时自动拷）
│   │   ├── index.html
│   │   ├── vite.config.js     ← outDir 指向 apps/family
│   │   └── package.json
│   └── patient/
│       ├── src/
│       ├── public/            ← 含 js/libopus.js + js/xiaozhi-client.js
│       ├── index.html
│       ├── vite.config.js     ← outDir 指向 apps/patient
│       └── package.json
│
├── apps/                      ← 构建输出（后端直接 serve 静态）
│   ├── family/                ← npm run build 的产物，不要手工改
│   ├── patient/               ← 同上
│   └── shared/
│       └── call-client.js     ← WebRTC 通话客户端，家属/患者共用
│
└── data/.config_hospice.yaml  ← 后端配置（端口、LLM、TTS、ASR 等）

mobile/                        ← Capacitor 原生壳工程
├── family/                    ← 家属端 APK 包壳
│   ├── capacitor.config.json  ← 里面写的 server.url = 后端局域网地址
│   ├── package.json
│   └── android/               ← npx cap add android 后生成，进 Android Studio 打包
└── patient/                   ← 患者端 APK 包壳，结构同上
```

**核心分工**：

- `apps-src/{family,patient}/` —— 前端 **源码**，日常开发改这里
- `apps/{family,patient}/` —— 前端 **构建产物**，后端静态路由 serve
- `mobile/{family,patient}/` —— Android **原生壳**，里面的 WebView 指向后端 URL 加载 `apps/*/index.html`

---

## 2. 后端启动

前端只有壳，API / SSE / WebSocket / 媒体文件全靠后端。任何开发/测试前都先把后端起起来。

```bash
cd main/xiaozhi-server
python app.py --config hospice
```

- 绑定 `0.0.0.0:8003`（见 `.config_hospice.yaml`）
- Windows 第一次启动会弹防火墙提示，选"允许"，否则手机连不上
- 确认局域网 IP：`ipconfig` 找 `IPv4 地址`，比如 `192.168.1.7`
- 浏览器访问 `http://<局域网 IP>:8003/family/index.html` 能打开即 OK

---

## 3. 日常开发流程

每个前端工程都是独立的 Vite 项目，第一次先装依赖：

```bash
cd main/xiaozhi-server/apps-src/family
npm install

cd ../patient
npm install
```

### 3.1 带热更新的 dev 模式

改 UI 的时候跑 dev server，保存文件秒级刷新（HMR），不用重启：

```bash
# 家属端
cd main/xiaozhi-server/apps-src/family
npm run dev                    # 默认端口 5555

# 患者端（新开一个终端）
cd main/xiaozhi-server/apps-src/patient
npm run dev                    # 默认端口 5556
```

打开浏览器：
- 家属端 `http://localhost:5555`
- 患者端 `http://localhost:5556`

API、SSE、`/shared/`、`/hospice-media/`（患者端多一条 `/test-assets/`）都被 Vite proxy 自动转给后端 8003，**所以后端必须同时开着**。

### 3.2 改代码后推到真机

dev 模式只对 `localhost` 浏览器生效。真机（APK / 手机浏览器 / 患者平板）用的是后端 serve 的生产 bundle —— 需要重新构建：

```bash
cd main/xiaozhi-server/apps-src/family
npm run build
```

- 构建产物直接写到 `main/xiaozhi-server/apps/family/`（`emptyOutDir: true`，会清空旧产物）
- 构建时 `public/` 下的 `manifest.json` / `sw.js` / `js/*` 会自动被拷进来
- 大约 1 秒完成
- **APK 不需要重打**：壳只是 WebView，代码换了手机关掉 App 重开就是新版本

患者端同理：`cd apps-src/patient && npm run build`。

---

## 4. 手机连 dev server（绕过 HMR 限制）

上面的 HMR 只对 `localhost` 生效。如果想让手机**实时看**你改的代码（不走"build → 刷新手机"的循环），有两种办法：

### 4.1 让手机直接访问 Vite dev server

Vite 的 `server.host: true` 已经让 dev server 绑 `0.0.0.0`，所以手机浏览器打开 `http://<PC局域网IP>:5555` 或 `http://<PC局域网IP>:5556` 就能连到 Vite，HMR 也起作用。前提是 PC 防火墙放行 5555/5556。

⚠️ 注意：手机访问 Vite dev 时，HMR / API proxy 都走 Vite；只要后端也跑着，一切正常。

### 4.2 Capacitor 壳里临时切到 dev URL

改 `mobile/family/capacitor.config.json` 里 `server.url` 指向 `http://<PC>:5555`，重新 `npx cap sync && 装 APK`，然后 App 就直接加载 Vite dev server 内容。**改完别忘改回指向 8003 再重新打包发给用户**。

日常不推荐这么折腾，改完用 `npm run build` 推新版本最稳。

---

## 5. APK 打包

### 5.1 一次性准备

下载 Android Studio：https://developer.android.com/studio  
首次启动时让它把 SDK 自动装好，记下 SDK 路径（后面 Capacitor 会自动探测）。

### 5.2 家属端 APK

```bash
cd mobile/family

# 第一次
npm install               # 装 @capacitor/cli, core, android
npx cap add android       # 生成 android/ 原生工程（几分钟）
npx cap sync android      # 把 capacitor.config 同步进去

# 打开 Android Studio
npx cap open android
```

Android Studio 里：
1. 右下角等 Gradle 索引完
2. **Build → Build Bundle(s) / APK(s) → Build APK(s)**
3. 构建完在弹窗点 "locate" 就能看到 APK 文件：  
   `mobile/family/android/app/build/outputs/apk/debug/app-debug.apk`
4. 传手机上装（需允许"未知来源"）；或者插 USB 数据线 + 开发者模式 + USB 调试，在 Android Studio 里直接点 ▶ 跑到手机上

### 5.3 患者端 APK

流程完全一样，只是换个目录：

```bash
cd mobile/patient
npm install
npx cap add android
npx cap sync android
npx cap open android
```

然后同上 Build APK。

### 5.4 什么时候要重新打包 APK？

**大多数时候不需要**。以下情况才需要：

- 改了 `capacitor.config.json`（比如后端 IP 变了）
- 要换 App 图标 / 名字 / 启动图
- 加了 Capacitor 原生插件（如推送、后台 Service）
- 正式上线签名 release 版

**只改前端代码（`apps-src/`）不需要重打** —— 跑 `npm run build` 就行，手机 App 重开就是新版本。

---

## 6. 前后端 IP 切换速查

```
PC 换 WiFi / 重启 / 出差 → 局域网 IP 可能变了
```

出现"手机连不上"时，按顺序检查：

1. `ipconfig` 看 PC 当前 IPv4
2. 后端启动日志里输出的 `家属端面板: http://X.X.X.X:8003/family/...` 对比
3. 手机和 PC 在同一 WiFi
4. PC 防火墙放行 8003（以及 5555/5556 如果要连 Vite dev）
5. `mobile/{family,patient}/capacitor.config.json` 里 `server.url` 的 IP 是否匹配
   - 不匹配就改，然后 `npx cap sync android && npx cap open android` → Build APK → 重装手机

**推荐习惯**：以后用内网静态 IP 或路由器里给 PC 绑定 MAC → IP，这样长期不会变。

---

## 7. 常见问题

### "手机浏览器页面空白"

打开 Chrome → `chrome://inspect/#devices` → 找到 WebView → inspect → 看 Console 报错：
- 资源 404：检查 `npm run build` 有没有成功，`apps/{family,patient}/` 下文件是否齐全
- CORS / 被 SW 缓存了老版本：在 DevTools 的 Application → Clear storage

### "录音失败 / 摄像头失败"

- 手机 Chrome：`chrome://flags/#unsafely-treat-insecure-origin-as-secure` 把 `http://<PC>:8003` 加入白名单，重启 Chrome
- Capacitor APK：无所谓 HTTPS，WebView 绕过此限制；但要确认 Android 权限已授予
  - 首次进入录音 / 通话页应该会弹权限框
  - 如果误拒了：手机设置 → 应用 → 小暖 → 权限 → 开启麦克风 / 摄像头

### "SSE / WebSocket 老断"

- 不是问题，家属端和通话客户端都自带断线重连（3s 退避）
- 如果频繁断：检查路由器有没有把 WebSocket 闲置连接掐掉（25s keepalive ping 已经加了）

### "Vite 构建警告 can't be bundled without type=module"

正常警告，不是错误。我们有几个外部脚本（`/shared/call-client.js`、患者端的 `js/libopus.js`、`js/xiaozhi-client.js`）不走打包，原样保留。可以忽略。

---

## 8. 一键清单（对照用）

### 日常开发：
```bash
# 终端 1
cd main/xiaozhi-server && python app.py --config hospice

# 终端 2（改家属端时）
cd main/xiaozhi-server/apps-src/family && npm run dev

# 终端 3（改患者端时）
cd main/xiaozhi-server/apps-src/patient && npm run dev
```

### 推生产：
```bash
cd main/xiaozhi-server/apps-src/family && npm run build
cd main/xiaozhi-server/apps-src/patient && npm run build
# 手机上重开 App 即可
```

### 出新 APK（家属端）：
```bash
cd mobile/family
npx cap sync android
npx cap open android      # Android Studio → Build APK(s)
```

### 出新 APK（患者端）：
```bash
cd mobile/patient
npx cap sync android
npx cap open android      # Android Studio → Build APK(s)
```

---

## 9. 新机器首次部署（公司服务器 / 换电脑）

**什么情况下走这一节**：`git clone` 拿到干净的代码库、还没有跑过任何东西。

### 9.1 先装依赖

```bash
# 1. Python 后端（Python 3.10+，venv 可选）
cd main/xiaozhi-server
pip install -r requirements.txt

# 2. 前端两份工程
cd apps-src/family && npm ci
cd ../patient    && npm ci
```

`npm ci` 比 `npm install` 更严格，会完全按照 `package-lock.json` 装，保证版本和开发机一致。

### 9.2 建配置文件（含 API Key）

**真实的 `data/.config_hospice.yaml` 是 gitignore 的，不会随 git 过来**。从模板复制一份再填密钥：

```bash
cp data/.config_hospice.example.yaml data/.config_hospice.yaml
```

然后编辑 `data/.config_hospice.yaml`，把所有 `YOUR_XXX_HERE` 替换成真实值：

| 字段 | 来源 |
|---|---|
| `LLM.AliLLM.api_key` | [阿里云 DashScope](https://dashscope.console.aliyun.com/apiKey) |
| `ASR.AliyunBLStreamASR.api_key` | 同上（共用同一 key） |
| `TTS.HuoshanDoubleStreamTTS.appid` / `access_token` | [火山引擎语音](https://console.volcengine.com/speech/app) |
| `plugins.get_weather.api_host` / `api_key` | [和风天气](https://console.qweather.com/) |

这些 key 不要直接贴进任何 markdown / issue / 聊天，只在本机这个文件里。

### 9.3 构建前端

```bash
cd main/xiaozhi-server/apps-src/family && npm run build
cd ../patient && npm run build
```

产物自动落到 `apps/family/` 和 `apps/patient/`，后端拿来 serve。**没构建的话访问前端页面会 404**。

### 9.4 启动服务器

```bash
cd main/xiaozhi-server
python app.py --config hospice
```

日志里应看到：

```
家属端面板: http://192.168.X.X:8003/family/index.html
患者端 PWA: http://192.168.X.X:8003/patient/index.html
```

### 9.5 出 APK（如果这台机器也要做打包）

需要：

- Android Studio（首次启动自动下载 SDK）
- JDK 21+（大多数系统自带或 Android Studio 会带）

然后：

```bash
cd mobile/family
npm ci
# 把 capacitor.config.json 里的 192.168.1.7 改成这台机器的实际局域网 IP
npx cap add android
npx cap sync android
npx cap open android    # Android Studio 里 Build APK
```

患者端同理（`cd mobile/patient`）。

**注意：`mobile/*/android/` 是 gitignored 的**，每台新机器都要 `npx cap add android` 重新生成。这是 Capacitor 的标准做法，原生工程不该进 git。

### 9.6 防火墙 / 网络

- 后端默认绑 `0.0.0.0:8003`（`http_port`）和 `0.0.0.0:8000`（小暖 WebSocket），两个端口都要在服务器防火墙放行
- 公司内网如果有代理 / VPN，可能干扰局域网 IP 探测，测试时优先确认 `ipconfig` 看到的 IP 在同段网络

### 9.7 数据目录初始化

首次启动时会自动创建：

- `data/hospice_sessions.db` —— SQLite 文件，自动 migration
- `data/hospice_media/` —— 家属/患者上传的照片/语音/视频

**这两个都是 gitignored**。生产环境长期运行后会积累数据；备份方案自己决定（最简单：定时 `tar` 打包这两个路径）。

---

## 10. Git 版本控制要点

### 不进 Git 的东西

| 路径 | 原因 |
|---|---|
| `main/xiaozhi-server/apps/family/`、`apps/patient/` | 构建产物，`npm run build` 重新生成 |
| `main/xiaozhi-server/data/hospice_sessions.db` | 运行时数据 + 隐私 |
| `main/xiaozhi-server/data/hospice_media/` | 用户上传的照片/视频（可能几百 MB） |
| `main/xiaozhi-server/data/.config_hospice.yaml` | 含 API 密钥 |
| `mobile/*/android/` | Capacitor 生成的原生工程 |
| `mobile/*/node_modules/`、`apps-src/*/node_modules/` | npm 依赖 |

### 要进 Git

| 路径 | 备注 |
|---|---|
| `main/xiaozhi-server/apps-src/` | 前端源码 |
| `main/xiaozhi-server/apps/shared/` | 家属/患者共用的 `call-client.js`，手写文件 |
| `main/xiaozhi-server/core/api/hospice/` | 后端 API + 存储层 |
| `main/xiaozhi-server/core/providers/emotion/` | 情绪解析 |
| `main/xiaozhi-server/data/.config_hospice.example.yaml` | 配置模板（脱敏） |
| `mobile/*/capacitor.config.json`、`package.json`、`package-lock.json` | Capacitor 壳配置 |
| `mobile/*/www/` | Capacitor 占位壳（极小） |

### 首次 commit 建议粒度

hospice 这批改动如果一次性 commit 会 5000 行巨无霸，建议拆：

```bash
# 先单独提 gitignore 改动
git add .gitignore
git commit -m "chore: add hospice ignore rules"

# 后端核心
git add main/xiaozhi-server/app.py main/xiaozhi-server/config/ \
        main/xiaozhi-server/core/connection.py \
        main/xiaozhi-server/core/http_server.py \
        main/xiaozhi-server/core/api/hospice/ \
        main/xiaozhi-server/core/providers/emotion/ \
        main/xiaozhi-server/apps/shared/
git commit -m "feat(hospice): 后端 API、会话日志、情绪解析、WebRTC 信令"

# 配置模板
git add main/xiaozhi-server/data/.config_hospice.example.yaml
git commit -m "chore(hospice): 配置文件模板"

# 前端
git add main/xiaozhi-server/apps-src/
git commit -m "feat(hospice): 家属端 + 患者端 Vite 前端"

# Capacitor 壳
git add mobile/
git commit -m "feat(hospice): Android APK 壳（家属 + 患者）"

# 文档
git add mobile/hospice-frontend-runbook.md
git commit -m "docs(hospice): 开发和部署手册"
```

### 分支策略建议

- 这个 repo 原本 fork 自 `xinnan-tech/xiaozhi-esp32-server`，长期会有上游更新
- hospice 功能建议在独立分支 `hospice/main` 维护，公司部署就用这个分支
- `main` 分支定期 `git pull upstream main` 同步上游，避免日后 merge 爆炸
- 具体做不做看你，当下首要是先把改动 push 起来
