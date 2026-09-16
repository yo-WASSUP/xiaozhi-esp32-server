# 腾讯云南京服务器部署步骤

这份文档只针对当前这台服务器。

已确认的信息：

- Ubuntu 24.04，8 核、32 GB 内存，当前可用内存约 23 GB；
- 系统盘 99 GB，剩余约 57 GB；
- Nginx、FFmpeg、Git、Node.js 18、Conda、Certbot 已安装；
- `8000` 已被 `/home/ubuntu/Good-Coach/backend/run.py` 占用；
- `api.sasamali.cn` 正通过 Nginx 转发到现有的 `8000` 服务；
- `18000` 和 `18003` 当前空闲，本项目使用这两个端口；
- 部署目录使用 `/home/ubuntu/test/xiaozhi-esp32-server`；
- 部署分支为 `feature/dignity-therapy`；
- `/home/ubuntu/test/` 当前为空。

模型继续使用云 API。只安装 Silero VAD 所需的 CPU 版 PyTorch，不配置 CUDA。

## 1. 上传部署包

不要在服务器下载整个 GitHub 仓库。开发机完成三个前端构建后生成运行包：

```powershell
cd F:\job-in-cn\xiaozhi-esp32-server\main\xiaozhi-server

cd apps-src\patient
npm run build
cd ..\family
npm run build
cd ..\clinician
npm run build

cd ..\..
.\scripts\create_deployment_bundle.ps1
```

生成文件：`dist\xiaozhi-hospice-deploy.tar.gz`。发布包不包含 Git 历史、管理端源码、测试模型、Node.js 依赖和私密运行数据。

首次部署可通过腾讯云终端的文件上传功能，把发布包上传到 `/home/ubuntu/test/`。以后将发布包上传到腾讯云 COS，服务器从 COS 下载，可以避开 GitHub 的境外链路。

在服务器解压：

```bash
cd /home/ubuntu/test

# 如果之前克隆失败，保留失败目录并腾出目标路径
if [ -d xiaozhi-esp32-server ]; then
  mv xiaozhi-esp32-server "xiaozhi-esp32-server.clone-failed-$(date +%s)"
fi

mkdir -p xiaozhi-esp32-server/main/xiaozhi-server
tar -xzf xiaozhi-hospice-deploy.tar.gz \
  -C xiaozhi-esp32-server/main/xiaozhi-server

test -f xiaozhi-esp32-server/main/xiaozhi-server/app.py \
  && echo "部署包解压完成"
```

## 2. 创建 Python 环境

服务器已有 Conda，创建独立的 Python 3.10 环境：

```bash
conda create -n xiaozhi_hospice python=3.10 -y
conda activate xiaozhi_hospice

cd /home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server
python -m pip install --upgrade pip wheel setuptools \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --timeout 120 --retries 10
```

先安装 CPU 版 PyTorch，再安装其余依赖：
```bash
pip install torch==2.2.2 torchaudio==2.2.2 \
  --index-url https://download.pytorch.org/whl/cpu \
  --timeout 120 --retries 10

pip install -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --timeout 120 --retries 10
```

普通 Python 依赖走清华 PyPI 镜像。CPU 版 PyTorch 保留官方独立源，避免安装到包含 CUDA 依赖的构建。

## 3. 检查三个前端

前端已包含在部署包中：

```bash
ls /home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server/apps/patient/index.html
ls /home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server/apps/family/index.html
ls /home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server/apps/clinician/index.html
```

## 4. 配置服务

```bash
cd /home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server
cp config.yaml data/.config.yaml
cp data/.config_hospice.example.yaml data/.config_hospice.yaml
nano .private_config.yaml
```

`data/.config.yaml` 供程序启动早期的日志模块读取；业务服务仍由 `--config hospice` 加载 `data/.config_hospice.yaml`。

写入以下配置。把 `YOUR_DOMAIN` 换成备案完成后的新域名，把密钥和密码换成真实值：

```yaml
server:
  ip: 127.0.0.1
  port: 18000
  http_port: 18003
  auth_key: "至少32字符的随机密钥"
  websocket: "wss://anantherapy.fun/xiaozhi/v1/"
  vision_explain: "https://anantherapy.fun/mcp/vision/explain"

```
豆包实时语音密钥写入：
```bash
nano data/.doubao_s2s.env
```

限制私密配置的读取权限：
```bash
chmod 600 .private_config.yaml data/.config_hospice.yaml data/.doubao_s2s.env
```

不要把开发机当前的 `.config_hospice.yaml` 原样上传。它可能包含局域网证书路径、测试密码和旧密钥。公网 HTTPS 交给 Nginx，因此服务器配置中不启用 `server.tls`。

## 5. 首次启动

```bash
conda activate xiaozhi_hospice
cd /home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server
python app.py --config hospice
```

另开一个终端验证：

```bash
curl -I http://127.0.0.1:18003/patient/index.html
curl -I http://127.0.0.1:18003/family/index.html
curl -I http://127.0.0.1:18003/clinician/index.html
```

页面都能返回后，按 `Ctrl+C` 停止前台进程。

## 6. 配置后台运行

创建服务文件：

```bash
sudo nano /etc/systemd/system/xiaozhi-hospice.service
```

内容如下：

```ini
[Unit]
Description=Xiaozhi Hospice Test Service
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/test/xiaozhi-esp32-server/main/xiaozhi-server
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/miniconda3/envs/xiaozhi_hospice/bin/python app.py --config hospice
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动并查看日志：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xiaozhi-hospice
sudo systemctl status xiaozhi-hospice --no-pager
sudo journalctl -u xiaozhi-hospice -n 100 --no-pager
```

## 7. 域名备案完成后接入 Nginx

先把新域名的 A 记录解析到服务器公网 IP `146.56.202.129`，然后新建独立配置，不改现有的 `goodcoach` 配置：

```bash
sudo nano /etc/nginx/sites-available/xiaozhi-hospice
```

内容如下，将 `YOUR_DOMAIN` 替换为新域名：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name anantherapy.fun;

    client_max_body_size 210m;

    location ^~ /xiaozhi/v1/ {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    location / {
        proxy_pass http://127.0.0.1:18003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

先在火山引擎 DNS 添加解析记录：

| 记录类型 | 主机记录 | 记录值 | TTL |
|---|---|---|---|
| A | `@` | `146.56.202.129` | 600 |

确认公网解析已经返回该 IP，再申请 HTTPS 证书：

```bash
sudo ln -s /etc/nginx/sites-available/xiaozhi-hospice \
  /etc/nginx/sites-enabled/xiaozhi-hospice
sudo nginx -t
sudo systemctl reload nginx

getent ahostsv4 anantherapy.fun
curl -I http://anantherapy.fun

sudo certbot --nginx -d anantherapy.fun
```

服务器已经安装 Certbot。证书成功后验证：

```bash
curl -I https://anantherapy.fun/patient/index.html
curl -I https://anantherapy.fun/family/index.html
curl -I https://anantherapy.fun/clinician/index.html
```

最终入口：

```text
https://anantherapy.fun/patient/index.html
https://anantherapy.fun/family/index.html
https://anantherapy.fun/clinician/index.html
https://anantherapy.fun/admin/index.html
wss://anantherapy.fun/xiaozhi/v1/
```

## 8. 后续更新代码

在开发机重新构建前端并运行 `scripts\create_deployment_bundle.ps1`。把新发布包上传到腾讯云 COS，服务器下载后执行：

```bash
cd /home/ubuntu/test
tar -xzf xiaozhi-hospice-deploy.tar.gz \
  -C xiaozhi-esp32-server/main/xiaozhi-server

sudo systemctl restart xiaozhi-hospice
sudo journalctl -u xiaozhi-hospice -n 100 --no-pager
```

私密配置、SQLite 数据库和上传媒体均在 Git 忽略范围内，更新代码时不要删除：

```text
.private_config.yaml
data/.config_hospice.yaml
data/.doubao_s2s.env
.hospice_auth.db*
data/hospice_sessions.db*
data/hospice_media/
```
