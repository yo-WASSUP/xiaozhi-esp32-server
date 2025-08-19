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

    // 从本地存储恢复设备配置
    loadDeviceConfig();

    // 生成随机MAC地址（如果本地存储中没有）
    if (!deviceMacInput.value) {
        const randomMac = utils.generateRandomMac();
        deviceMacInput.value = randomMac;
        displayMac.textContent = randomMac;
        // 立即保存新生成的MAC
        saveDeviceConfig();
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
            saveDeviceConfig(); // 自动保存
        });
    }

    // 监听客户端ID输入变化
    if (clientIdInput && displayClient) {
        clientIdInput.addEventListener('input', (e) => {
            displayClient.textContent = e.target.value || 'web_test_client';
            saveDeviceConfig(); // 自动保存
        });
    }

    // 监听设备名称变化
    const deviceNameInput = document.getElementById('deviceName');
    if (deviceNameInput) {
        deviceNameInput.addEventListener('input', () => {
            saveDeviceConfig(); // 自动保存
        });
    }

    // 监听Token变化
    const tokenInput = document.getElementById('token');
    if (tokenInput) {
        tokenInput.addEventListener('input', () => {
            saveDeviceConfig(); // 自动保存
        });
    }
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

// 保存设备配置到本地存储
function saveDeviceConfig() {
    try {
        const deviceMacInput = document.getElementById('deviceMac');
        const deviceNameInput = document.getElementById('deviceName');
        const clientIdInput = document.getElementById('clientId');
        const tokenInput = document.getElementById('token');

        const config = {
            deviceMac: deviceMacInput?.value || '',
            deviceName: deviceNameInput?.value || 'Web测试设备',
            clientId: clientIdInput?.value || 'web_test_client',
            token: tokenInput?.value || 'your-token1',
            lastSaved: new Date().toISOString()
        };

        localStorage.setItem('deviceConfig', JSON.stringify(config));
        utils.log('设备配置已保存', 'debug');
    } catch (error) {
        utils.log(`保存设备配置失败: ${error.message}`, 'warning');
    }
}

// 从本地存储加载设备配置
function loadDeviceConfig() {
    try {
        const saved = localStorage.getItem('deviceConfig');
        if (!saved) {
            utils.log('未找到保存的设备配置', 'debug');
            return false;
        }

        const config = JSON.parse(saved);
        
        const deviceMacInput = document.getElementById('deviceMac');
        const deviceNameInput = document.getElementById('deviceName');
        const clientIdInput = document.getElementById('clientId');
        const tokenInput = document.getElementById('token');

        if (deviceMacInput && config.deviceMac) {
            deviceMacInput.value = config.deviceMac;
        }
        if (deviceNameInput && config.deviceName) {
            deviceNameInput.value = config.deviceName;
        }
        if (clientIdInput && config.clientId) {
            clientIdInput.value = config.clientId;
        }
        if (tokenInput && config.token) {
            tokenInput.value = config.token;
        }

        utils.log(`已恢复设备配置，上次保存时间: ${config.lastSaved}`, 'success');
        return true;
    } catch (error) {
        utils.log(`加载设备配置失败: ${error.message}`, 'warning');
        return false;
    }
}

// 清除保存的设备配置
function clearDeviceConfig() {
    try {
        localStorage.removeItem('deviceConfig');
        utils.log('设备配置已清除', 'info');
        
        // 重新初始化配置
        initConfigPanel();
    } catch (error) {
        utils.log(`清除设备配置失败: ${error.message}`, 'error');
    }
}

// 导出到全局
window.config = {
    getConfig,
    validateConfig,
    initConfigPanel,

    initTabs,
    saveDeviceConfig,
    loadDeviceConfig,
    clearDeviceConfig
};