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

## 4. APK 打包

### 4.1 一次性准备

下载 Android Studio：https://developer.android.com/studio  
首次启动时让它把 SDK 自动装好，记下 SDK 路径（后面 Capacitor 会自动探测）。

### 4.2 家属端 APK

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

---

## 11. HTTPS（手机真机 + 通话必备）

**什么时候需要**：手机 APK / 局域网外的浏览器里要用**麦克风/摄像头**（通话、录音功能）。浏览器和 Android WebView 的安全上下文规则：除 `http://localhost` 外的 HTTP 页面拿不到 `navigator.mediaDevices`，`getUserMedia` 直接报错。

### 11.1 准备 mkcert

mkcert 会在你的电脑和所有需要用到这个服务的手机上，各自安装一次"本机根 CA"，然后给局域网 IP 签发"浏览器信任"的证书。不像纯自签证书到处会弹"不安全"警告。

**电脑端（只装一次）**：

```bash
# Windows（用 chocolatey 或 scoop）
scoop install mkcert
# 或 choco install mkcert
# 或直接从 https://github.com/FiloSottile/mkcert/releases 下载 .exe 放 PATH 里

# 安装本机根 CA 到系统信任库
mkcert -install
```

### 11.2 给局域网 IP 签证书

```bash
cd main/xiaozhi-server
mkdir -p data/certs
cd data/certs

# 把你电脑的局域网 IP 换掉（ipconfig 查 IPv4）
mkcert 192.168.1.7 localhost 127.0.0.1
```

会生成两个文件：

```
192.168.1.7+2.pem       ← 证书
192.168.1.7+2-key.pem   ← 私钥
```

名字里的 `+2` 表示"主机名 + 2 个额外 SAN"，版本不同可能是 `+N`，对应往后用。

### 11.3 在 `.config_hospice.yaml` 里启用

```yaml
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  tls:
    cert_file: data/certs/192.168.1.7+2.pem
    key_file:  data/certs/192.168.1.7+2-key.pem
```

**重启后端** (`python app.py --config hospice`)，日志里 URL 前缀应该变成 `https://` 了：

```
家属端面板: https://192.168.1.7:8003/family/index.html
患者端 PWA: https://192.168.1.7:8003/patient/index.html
```

证书文件不存在或加载失败时会自动回退到 HTTP 并打印 WARNING，日志里一眼能看见。

### 11.4 手机上装根 CA（关键步骤）

只在电脑装 CA 还不够，**手机需要单独装一次**，否则 Android WebView 打开 `https://...` 会报"证书不信任"。

1. **拿到根证书文件**：
   ```bash
   mkcert -CAROOT
   # 输出类似：C:\Users\38370\AppData\Local\mkcert
   ```
   这个目录下有 `rootCA.pem`。

2. **改扩展名为 `.crt`**（Android 对扩展名敏感）：
   ```bash
   cp "C:\Users\38370\AppData\Local\mkcert\rootCA.pem" C:\Users\38370\Desktop\mkcert-root.crt
   ```

3. **把 `mkcert-root.crt` 拷到手机**（微信发给自己 / QQ 文件传输 / 邮件附件 / 数据线都行）

4. **手机上打开这个 crt 文件 → 系统弹出"安装证书"对话框**：
   - 设置 → 安全 → 加密与凭据 → 安装证书 → CA 证书
   - 选 "VPN 和应用"（不是 WLAN）
   - 给证书随便起个名字（比如 "mkcert 小暖开发"）
   - 不同品牌路径略有差异，搜 "安装 CA 证书" + 你的手机型号

5. **装好后** 打开手机 Chrome 访问 `https://192.168.1.7:8003/family/index.html`，**地址栏应该是小锁图标，没有红色警告**。

### 11.5 更新 APK 让 WebView 认这个 CA

**关键**：Android 7+ 起，**App 默认不信任用户安装的 CA** —— 只信系统自带 CA。所以即使手机装好了 mkcert 根证书，Capacitor WebView 打开 `https://` 还是会报错。

要让 APK 信任用户 CA，在 `mobile/family/android/app/src/main/res/xml/network_security_config.xml` 加一个文件（如果目录没有就创建）：

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
```

然后在 `android/app/src/main/AndroidManifest.xml` 的 `<application>` 标签加上引用：

```xml
<application
    ...
    android:networkSecurityConfig="@xml/network_security_config"
    ...>
```

重新 Build APK → 装到手机。现在 WebView 就会接受 mkcert 签的证书。

### 11.6 Capacitor config 换 https

```json
// mobile/family/capacitor.config.json
{
  "server": {
    "url": "https://192.168.1.7:8003/family/index.html",
    ...
  }
}
```

patient 同理。修改后 `npx cap sync android` → Build APK → 装手机。

### 11.7 验证全链路

1. PC 浏览器打开 `https://192.168.1.7:8003/family/index.html` → 没有证书警告 ✓
2. 手机 Chrome 打开同一地址 → 没警告 ✓（没警告 = 11.4 装对了）
3. APK 打开家属端 → 直接进主界面（没提示"Net::ERR_CERT_AUTHORITY_INVALID"）✓（没错 = 11.5 做对了）
4. 点拨号 → 能正常获取麦克风/摄像头权限 → 发起通话 → 患者端接听 → 通话打通 ✓

### 11.8 IP 变了怎么办

**重新签一套证书**：

```bash
cd main/xiaozhi-server/data/certs
rm *.pem
mkcert 192.168.X.X localhost 127.0.0.1
```

然后改 `.config_hospice.yaml` 里的文件名（因为可能从 `+2` 变成 `+3`）、改 capacitor.config.json 里的 IP、重打 APK。

**建议**：局域网路由器里给 PC 绑定静态 IP，一劳永逸。