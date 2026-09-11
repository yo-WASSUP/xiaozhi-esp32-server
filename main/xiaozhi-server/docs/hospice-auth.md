# 安宁疗护账号登录

普通账号保存在 SQLite 数据库 `data/hospice_sessions.db`，密码只保存 PBKDF2 哈希。管理员账号和密码由配置文件提供。

## 启用配置

在当前使用的 hospice 配置中加入：

```yaml
hospice:
  db_path: data/hospice_sessions.db
  auth:
    enabled: true
    secret_key: "请替换为随机生成的至少32字符密钥"
    admin_username: admin
    admin_password: "请设置至少8个字符的管理员密码"
    access_token_seconds: 43200
    refresh_token_seconds: 2592000
    max_failed_attempts: 5
    lock_seconds: 600
```

修改配置后重启服务，访问 `/admin/index.html`。管理员可以创建患者、家属、医护账号，设置患者设备权限、重置密码和停用账号。

管理员密码以明文存在配置文件中。公网服务器应限制配置文件只允许服务账号和运维人员读取，并使用 HTTPS。反向代理需要保留 `Cookie`、`Set-Cookie` 和 WebSocket Upgrade 请求头。

家属也可以通过患者端生成的 6 位配对码获得患者权限；解除配对后，配对产生的权限同步撤销。

## 界面地址

- 管理员端：`/admin/index.html`
- 医护端：`/clinician/index.html`
- 患者端：`/patient/index.html`
- 家属端：`/family/index.html`

启用登录后，浏览器语音 WebSocket 同样校验患者账号。若接入 ESP32 等无浏览器登录能力的实体设备，需要把设备 ID 加入 `server.auth.allowed_devices`。
