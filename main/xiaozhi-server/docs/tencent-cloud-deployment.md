# 腾讯云南京测试环境部署手册

本文用于把当前“安安”服务部署到现有腾讯云南京 CVM。该实例同时运行其他项目，因此部署过程使用独立目录、独立 Python 虚拟环境、独立 systemd 服务，并复用现有 Nginx。语音识别、语言模型和语音合成继续调用云 API，不安装 NVIDIA 驱动、CUDA 或 GPU 版 PyTorch。

## 1. 最终结构

假设正式域名为 `example.com`，实际操作时统一替换：

```text
https://example.com/patient/index.html    患者端
https://example.com/family/index.html     家属端
https://example.com/clinician/index.html  医护端
wss://example.com/xiaozhi/v1/             设备语音 WebSocket

Nginx :443
├── /xiaozhi/v1/  -> 127.0.0.1:8000
└── 其他请求       -> 127.0.0.1:8003
```

公网安全组只开放 `80/tcp`、`443/tcp` 和受限来源的 SSH 端口。`8000`、`8003` 不直接暴露到公网。

## 2. 开始前的四个条件

1. 新域名已完成实名认证，并按腾讯云流程提交备案。服务器在腾讯云南京，备案接入商应选择腾讯云；域名注册商可以是火山引擎或腾讯云。
2. 已确认当前代码可形成一个部署版本。当前开发机工作区含未提交、未跟踪文件，直接在服务器克隆仓库会缺少这些内容。先整理一次部署提交并推送到 `origin`，其中应包含三个前端源码和必要模型文件；不得包含真实密钥、数据库、上传媒体及测试患者数据。
3. 拿到服务器 SSH 登录方式，并确认 GitHub 仓库的读取方式。私有仓库优先使用只读 Deploy Key。
4. 准备新的公网测试密码和至少 32 字符的随机密钥。不要继续使用局域网测试账号的初始密码。

## 3. 只读检查现有服务器

先登录服务器，仅执行检查：

```bash
cat /etc/os-release
uname -m
df -h
free -h
uptime
ss -lntup
systemctl --type=service --state=running
nginx -v
sudo nginx -T
python3 --version
node --version
git --version
ffmpeg -version
```

记录以下结果后再安装：

- `80/443/8000/8003` 是否已占用；
- 当前 Nginx 配置文件位置和已有域名；
- 磁盘至少保留 15 GB，内存至少保留 4 GB；
- 现有项目的用户、目录和 systemd 服务名。

如果 `8000` 或 `8003` 已占用，先给本项目换成一组未占用端口，例如 `18000/18003`，同时修改后文配置和 Nginx upstream。不要停止旧项目抢占端口。

## 4. 安装基础环境

以下以 Ubuntu 22.04 为例。已有的软件跳过，不升级整台服务器：

```bash
sudo apt update
sudo apt install -y git ffmpeg libopus0 python3.10 python3.10-venv python3-pip nginx
```

Node.js 只用于构建三个前端。若服务器已有 Node.js 20，可直接使用；版本过旧时再安装 Node.js 20。构建完成后，Python 服务不依赖 Node 常驻运行。

创建隔离的服务账号和目录：

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin xiaozhi
sudo mkdir -p /opt/xiaozhi-hospice
sudo chown -R xiaozhi:xiaozhi /opt/xiaozhi-hospice
```

## 5. 获取部署版本

推荐从已整理并推送的 Git 分支部署：

```bash
sudo -u xiaozhi git clone --branch <DEPLOY_BRANCH> --single-branch \
  https://github.com/yo-WASSUP/xiaozhi-esp32-server.git \
  /opt/xiaozhi-hospice/repo

cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server
```

私有仓库不要把 GitHub 密码或访问令牌直接写进命令。配置只读 Deploy Key 后改用 SSH 地址克隆。

每次部署记录确定的提交号：

```bash
git rev-parse HEAD
git status --short
```

服务器上的代码目录应保持干净，真实配置和业务数据由 `.gitignore` 排除。

## 6. 创建 CPU Python 环境

```bash
cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server
sudo -u xiaozhi python3.10 -m venv /opt/xiaozhi-hospice/venv
sudo -u xiaozhi /opt/xiaozhi-hospice/venv/bin/python -m pip install --upgrade pip wheel setuptools
```

先安装 CPU 版 PyTorch，再安装项目依赖。这样不会拉取 CUDA 运行库：

```bash
sudo -u xiaozhi /opt/xiaozhi-hospice/venv/bin/pip install \
  torch==2.2.2 torchaudio==2.2.2 \
  --index-url https://download.pytorch.org/whl/cpu

sudo -u xiaozhi /opt/xiaozhi-hospice/venv/bin/pip install -r requirements.txt
```

这里保留 CPU 版 PyTorch，是因为本地 Silero VAD 需要它。ASR、LLM、TTS 仍走 API。症状语义检索使用 ONNX CPU；若部署提交未包含 `models/bge-small-zh-v1.5`，执行：

```bash
sudo -u xiaozhi /opt/xiaozhi-hospice/venv/bin/python scripts/setup_symptom_model.py
```

## 7. 构建三个前端

```bash
cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server/apps-src/patient
sudo -u xiaozhi npm ci
sudo -u xiaozhi npm run build

cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server/apps-src/family
sudo -u xiaozhi npm ci
sudo -u xiaozhi npm run build

cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server/apps-src/clinician
sudo -u xiaozhi npm ci
sudo -u xiaozhi npm run build
```

构建结果应分别存在：

```text
apps/patient/index.html
apps/family/index.html
apps/clinician/index.html
```

## 8. 创建服务器私密配置

基础配置从模板复制，真实密钥放进被 Git 忽略的覆盖文件：

```bash
cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server
sudo -u xiaozhi cp data/.config_hospice.example.yaml data/.config_hospice.yaml
sudo -u xiaozhi nano .private_config.yaml
```

`.private_config.yaml` 至少填写以下内容，所有占位符都换成新值：

```yaml
server:
  auth_key: "<随机生成的至少32字符密钥>"
  websocket: "wss://example.com/xiaozhi/v1/"
  vision_explain: "https://example.com/mcp/vision/explain"

hospice:
  auth:
    enabled: true
    secret_key: "<另一条随机生成的至少32字符密钥>"
    admin_username: "<新管理员用户名>"
    admin_password: "<新管理员强密码>"

LLM:
  AliLLM:
    api_key: "<DashScope API Key>"

ASR:
  AliyunBLStreamASR:
    api_key: "<DashScope API Key>"

TTS:
  AliBLTTS:
    api_key: "<DashScope API Key>"
  HuoshanDoubleStreamTTS:
    appid: "<火山引擎 App ID>"
    access_token: "<火山引擎 Access Token>"
```

豆包实时语音密钥单独写入：

```bash
sudo -u xiaozhi nano data/.doubao_s2s.env
```

文件内容：

```dotenv
DOUBAO_API_KEY=<豆包实时语音 API Key>
```

收紧权限：

```bash
sudo chown xiaozhi:xiaozhi .private_config.yaml data/.config_hospice.yaml data/.doubao_s2s.env
sudo chmod 600 .private_config.yaml data/.config_hospice.yaml data/.doubao_s2s.env
```

部署时不要直接复制开发机当前的 `.config_hospice.yaml`：里面可能含局域网自签证书路径、旧密码和旧密钥。公网 TLS 在 Nginx 终止，Python 端不配置 `server.tls`。

## 9. 首次启动和本机检查

先以前台方式启动，看到服务完成初始化后再交给 systemd：

```bash
cd /opt/xiaozhi-hospice/repo/main/xiaozhi-server
sudo -u xiaozhi /opt/xiaozhi-hospice/venv/bin/python app.py --config hospice
```

另开一个 SSH 窗口执行：

```bash
curl -i http://127.0.0.1:8003/patient/index.html
curl -i http://127.0.0.1:8003/family/index.html
curl -i http://127.0.0.1:8003/clinician/index.html
curl -i http://127.0.0.1:8003/xiaozhi/ota/
```

前台检查通过后按 `Ctrl+C` 停止。

## 10. 配置 systemd

创建 `/etc/systemd/system/xiaozhi-hospice.service`：

```ini
[Unit]
Description=Xiaozhi Hospice Test Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=xiaozhi
Group=xiaozhi
WorkingDirectory=/opt/xiaozhi-hospice/repo/main/xiaozhi-server
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/xiaozhi-hospice/venv/bin/python app.py --config hospice
Restart=on-failure
RestartSec=5
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
```

加载并检查：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xiaozhi-hospice
sudo systemctl status xiaozhi-hospice --no-pager
sudo journalctl -u xiaozhi-hospice -n 100 --no-pager
```

## 11. 备案完成前怎么测试

备案完成前先验证服务端启动、API 连通和页面文件，不把新域名正式开放。需要在自己电脑预览页面时，可使用 SSH 隧道：

```bash
ssh -L 8003:127.0.0.1:8003 -L 8000:127.0.0.1:8000 <SSH_USER>@146.56.202.129
```

然后访问 `http://localhost:8003/patient/index.html`。该方式适合页面和基础接口检查。完整的手机麦克风、摄像头、PWA 和公网 WebSocket 验收留到域名 HTTPS 生效后进行。

## 12. 备案完成后配置 Nginx

先把域名的 A 记录解析到 `146.56.202.129`。确认解析生效后，为新域名单独创建 Nginx server block，不修改旧项目的 server block。

`/etc/nginx/sites-available/xiaozhi-hospice`：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name example.com;

    client_max_body_size 210m;

    location ^~ /xiaozhi/v1/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass http://127.0.0.1:8003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

启用配置前先检查冲突：

```bash
sudo ln -s /etc/nginx/sites-available/xiaozhi-hospice /etc/nginx/sites-enabled/xiaozhi-hospice
sudo nginx -t
sudo systemctl reload nginx
```

不要删除现有 Nginx 配置。若已有统一的配置目录或面板生成配置，应沿用现有管理方式，把上面的两个 `location` 合入新域名的独立站点。

## 13. 配置 HTTPS

可以使用腾讯云免费证书或 Certbot。使用 Certbot 时：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

证书签发完成后，确认 Nginx 已监听 443 并将 HTTP 重定向到 HTTPS。不要在 Python 服务里再次启用自签 TLS。

## 14. 公网验收

依次验证：

```bash
curl -I https://example.com/patient/index.html
curl -I https://example.com/family/index.html
curl -I https://example.com/clinician/index.html
curl -i https://example.com/xiaozhi/ota/
```

再用手机流量执行完整业务验收：

- 三类测试账号登录、退出、令牌刷新；
- 患者端麦克风授权、唤醒词、ASR、LLM、TTS；
- 患者与家属的消息和媒体上传；
- 医护端查看数据；
- WebSocket 断线重连；
- 服务重启后账号、会话、媒体仍存在；
- 不同运营商网络下的音视频通话。

当前 WebRTC 只配置公共 STUN。跨运营商或严格 NAT 网络可能无法建立媒体连接。若公网通话是本轮必测功能，需要增加 coturn，并把 TURN 地址和凭据接入前端；这属于第二阶段配置。

## 15. 数据、日志和回滚

至少备份以下内容：

```text
.private_config.yaml
data/.config_hospice.yaml
data/.doubao_s2s.env
.hospice_auth.db*
data/hospice_sessions.db*
data/hospice_media/
```

查看日志：

```bash
sudo journalctl -u xiaozhi-hospice -f
tail -f /opt/xiaozhi-hospice/repo/main/xiaozhi-server/tmp/server.log
```

每次更新前记录当前提交号。更新过程：停止服务、备份数据、拉取指定提交、按需重建依赖和前端、启动并验收。回滚时切回上一个已验证提交并恢复对应数据备份，不覆盖旧项目目录和配置。

## 16. 本轮执行顺序

1. 整理并推送当前完整代码版本。
2. 重新登录腾讯云终端，对服务器执行第 3 节只读检查。
3. 根据端口和 Nginx 检查结果确定最终端口。
4. 完成第 4 至第 10 节，先让服务在本机端口稳定运行。
5. 域名实名认证、备案与上述部署并行进行。
6. 备案通过后完成 DNS、Nginx、HTTPS 和公网验收。

