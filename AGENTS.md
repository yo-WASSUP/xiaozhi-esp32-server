# AGENTS.md
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

| 登录入口 | 账号 | 初始密码 |
|---|---|---|
| [患者端](https://192.168.20.2:8003/patient/index.html) | `test_patient01` | `Anan_P7m4!2026` |
| [家属端](https://192.168.20.2:8003/family/index.html) | `test_family01` | `Anan_F8k3!2026` |
| [医护端](https://192.168.20.2:8003/clinician/index.html) | `test_clinician01` | `Anan_C9r2!2026` |
三个账号均填写测试设备 ID：test-device-01