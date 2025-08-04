// 配置管理模块

// 获取设备配置
function getConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');
    const tokenInput = document.getElementById('token');
    
    return {
        deviceId: deviceMacInput?.value || utils.generateRandomMac(),
        deviceMac: deviceMacInput?.value || utils.generateRandomMac(),
        deviceName: deviceNameInput?.value || 'Web测试设备',
        clientId: clientIdInput?.value || 'web_test_client',
        token: tokenInput?.value || 'your-token1'
    };
}

// 验证配置
function validateConfig(config) {
    if (!config.deviceId || !config.deviceMac) {
        utils.log('错误：设备MAC地址不能为空', 'error');
        return false;
    }
    
    if (!config.clientId) {
        utils.log('错误：客户端ID不能为空', 'error');
        return false;
    }
    
    if (!config.token) {
        utils.log('错误：认证Token不能为空', 'error');
        return false;
    }
    
    return true;
}

// 初始化配置面板
function initConfigPanel() {
    const toggleButton = document.getElementById('toggleConfig');
    const configPanel = document.getElementById('configPanel');
    const deviceMacInput = document.getElementById('deviceMac');
    const clientIdInput = document.getElementById('clientId');
    const displayMac = document.getElementById('displayMac');
    const displayClient = document.getElementById('displayClient');
    
    // 从本地存储恢复URL设置
    const serverUrlInput = document.getElementById('serverUrl');
    const otaUrlInput = document.getElementById('otaUrl');
    
    const savedWsUrl = localStorage.getItem('wsUrl');
    const savedOtaUrl = localStorage.getItem('otaUrl');
    
    if (savedWsUrl && serverUrlInput) {
        serverUrlInput.value = savedWsUrl;
    }
    
    if (savedOtaUrl && otaUrlInput) {
        otaUrlInput.value = savedOtaUrl;
    }

    // 生成随机MAC地址（如果没有设置）
    if (!deviceMacInput.value) {
        const randomMac = utils.generateRandomMac();
        deviceMacInput.value = randomMac;
        displayMac.textContent = randomMac;
    } else {
        displayMac.textContent = deviceMacInput.value;
    }

    // 更新显示的客户端ID
    if (displayClient) {
        displayClient.textContent = clientIdInput.value || 'web_test_client';
    }

    // 折叠/展开配置面板
    if (toggleButton && configPanel) {
        toggleButton.addEventListener('click', () => {
            const isExpanded = configPanel.classList.contains('expanded');
            if (isExpanded) {
                configPanel.classList.remove('expanded');
                toggleButton.textContent = '编辑';
            } else {
                configPanel.classList.add('expanded');
                toggleButton.textContent = '收起';
            }
        });
    }

    // 监听MAC地址输入变化
    if (deviceMacInput && displayMac) {
        deviceMacInput.addEventListener('input', (e) => {
            displayMac.textContent = e.target.value || '未设置';
        });
    }

    // 监听客户端ID输入变化
    if (clientIdInput && displayClient) {
        clientIdInput.addEventListener('input', (e) => {
            displayClient.textContent = e.target.value || 'web_test_client';
        });
    }
}

// 测试认证
async function testAuthentication() {
    const serverUrlInput = document.getElementById('serverUrl');
    const serverUrl = serverUrlInput.value.trim();
    
    if (!serverUrl) {
        utils.log('错误：请先填写服务器地址', 'error');
        return;
    }

    utils.log('开始测试认证配置...', 'info');
    utils.log('尝试不同认证参数的连接：', 'info');

    // 测试1: 无参数连接
    try {
        utils.log('测试1: 尝试无参数连接...', 'info');
        const ws1 = new WebSocket(serverUrl);

        ws1.onopen = () => {
            utils.log('测试1成功: 无参数可连接，服务器可能没有启用认证', 'success');
            ws1.close();
        };

        ws1.onerror = (error) => {
            utils.log('测试1失败: 无参数连接被拒绝，服务器可能启用了认证', 'error');
        };

        // 等待一段时间让连接尝试完成
        await new Promise(resolve => setTimeout(resolve, 2000));

    } catch (error) {
        utils.log(`测试1异常: ${error.message}`, 'error');
    }

    // 测试2: 带token参数连接
    try {
        utils.log('测试2: 尝试带token参数连接...', 'info');
        const config = getConfig();
        
        if (validateConfig(config)) {
            let url = new URL(serverUrl);
            url.searchParams.append('token', config.token);
            url.searchParams.append('device_id', config.deviceId);
            url.searchParams.append('device_mac', config.deviceMac);

            const ws2 = new WebSocket(url.toString());

            ws2.onopen = () => {
                utils.log('测试2成功: 带token参数可连接', 'success');

                // 尝试发送hello消息
                const helloMsg = {
                    type: 'hello',
                    device_id: config.deviceId,
                    device_mac: config.deviceMac,
                    token: config.token
                };

                ws2.send(JSON.stringify(helloMsg));
                utils.log('已发送hello消息，等待服务器回应...', 'info');
            };

            ws2.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    if (message.type === 'hello') {
                        utils.log('测试2成功: 服务器接受hello消息', 'success');
                        utils.log(`服务器回应: ${JSON.stringify(message, null, 2)}`, 'success');
                    }
                } catch (e) {
                    utils.log('服务器回应格式错误', 'warning');
                }
                ws2.close();
            };

            ws2.onerror = (error) => {
                utils.log('测试2失败: 带token参数连接被拒绝', 'error');
            };

            ws2.onclose = () => {
                utils.log('测试2连接已关闭', 'info');
            };
        }
    } catch (error) {
        utils.log(`测试2异常: ${error.message}`, 'error');
    }

    utils.log('认证测试完成', 'info');
}

// 初始化标签页
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.dataset.tab;
            
            // 移除所有活动状态
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // 激活点击的标签
            tab.classList.add('active');
            const targetContent = document.getElementById(`${targetTab}Tab`);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });
}

// 导出到全局
window.config = {
    getConfig,
    validateConfig,
    initConfigPanel,
    testAuthentication,
    initTabs
};