// UI管理模块

// 添加消息到会话记录
function addMessage(text, isUser = false) {
    const conversationDiv = document.getElementById('conversation');
    if (!conversationDiv) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'server'}`;
    messageDiv.textContent = text;
    conversationDiv.appendChild(messageDiv);
    conversationDiv.scrollTop = conversationDiv.scrollHeight;

    // 检查是否包含ROS2命令
    if (!isUser && window.ros2) {
        window.ros2.checkAndExecuteROS2Command(text);
    }
}

// 初始化可视化器
function initVisualizer() {
    const visualizerCanvas = document.getElementById('audioVisualizer');
    if (!visualizerCanvas) return;
    
    const visualizerContext = visualizerCanvas.getContext('2d');
    visualizerCanvas.width = visualizerCanvas.clientWidth;
    visualizerCanvas.height = visualizerCanvas.clientHeight;
    visualizerContext.fillStyle = '#fafafa';
    visualizerContext.fillRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);
}

// 绘制音频可视化效果
function drawVisualizer(dataArray, isRecording = false) {
    const visualizerCanvas = document.getElementById('audioVisualizer');
    if (!visualizerCanvas) return;
    
    const visualizerContext = visualizerCanvas.getContext('2d');
    
    if (!isRecording) return;

    if (window.audio && window.audio.analyser) {
        window.audio.analyser.getByteFrequencyData(dataArray);
    }

    visualizerContext.fillStyle = '#fafafa';
    visualizerContext.fillRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);

    const barWidth = (visualizerCanvas.width / dataArray.length) * 2.5;
    let barHeight;
    let x = 0;

    for (let i = 0; i < dataArray.length; i++) {
        barHeight = dataArray[i] / 2;

        visualizerContext.fillStyle = `rgb(${barHeight + 100}, 50, 50)`;
        visualizerContext.fillRect(x, visualizerCanvas.height - barHeight, barWidth, barHeight);

        x += barWidth + 1;
    }
}

// 更新录音按钮状态
function updateRecordButtonState(isRecording) {
    const recordButton = document.getElementById('recordButton');
    const stopButton = document.getElementById('stopButton');
    
    if (recordButton) {
        if (isRecording) {
            recordButton.classList.add('recording');
            recordButton.textContent = '录音中...';
            recordButton.disabled = true;
        } else {
            recordButton.classList.remove('recording');
            recordButton.textContent = '开始录音';
            recordButton.disabled = false;
        }
    }
    
    if (stopButton) {
        stopButton.disabled = !isRecording;
    }
}

// 显示连接状态
function showConnectionStatus(message, type = 'info') {
    const statusDiv = document.createElement('div');
    statusDiv.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background-color: ${type === 'success' ? '#d4edda' : type === 'error' ? '#f8d7da' : '#d1ecf1'};
        color: ${type === 'success' ? '#155724' : type === 'error' ? '#721c24' : '#0c5460'};
        border: 1px solid ${type === 'success' ? '#c3e6cb' : type === 'error' ? '#f5c6cb' : '#bee5eb'};
        border-radius: 5px;
        padding: 10px 20px;
        z-index: 1000;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    `;
    statusDiv.textContent = message;
    
    document.body.appendChild(statusDiv);
    
    // 3秒后自动移除
    setTimeout(() => {
        if (statusDiv.parentElement) {
            statusDiv.remove();
        }
    }, 3000);
}

// 清理所有临时UI元素
function cleanupUI() {
    // 移除所有临时提示
    const existingTips = document.querySelectorAll('[id$="-tip"]');
    existingTips.forEach(tip => tip.remove());
    
    // 移除状态提示
    const statusElements = document.querySelectorAll('[style*="position: fixed"]');
    statusElements.forEach(element => {
        if (element.id !== 'scriptStatus') {
            element.remove();
        }
    });
}

// 初始化事件监听器
function initEventListeners() {
    // 连接按钮
    const connectButton = document.getElementById('connectButton');
    if (connectButton) {
        connectButton.addEventListener('click', window.websocketManager.connectToServer);
    }
    
    // 认证测试按钮
    const authTestButton = document.getElementById('authTestButton');
    if (authTestButton) {
        authTestButton.addEventListener('click', window.config.testAuthentication);
    }
    
    // OTA测试按钮
    const otaTestButton = document.getElementById('otaTestButton');
    if (otaTestButton) {
        otaTestButton.addEventListener('click', testOTAConnection);
    }
    
    // 重置设备按钮
    const resetDeviceButton = document.getElementById('resetDeviceButton');
    if (resetDeviceButton) {
        resetDeviceButton.addEventListener('click', resetDevice);
    }
    
    // 文本发送按钮
    const sendTextButton = document.getElementById('sendTextButton');
    if (sendTextButton) {
        sendTextButton.addEventListener('click', window.websocketManager.sendTextMessage);
    }
    
    // 录音按钮
    const recordButton = document.getElementById('recordButton');
    if (recordButton) {
        recordButton.addEventListener('click', () => {
            if (window.audio) {
                window.audio.startRecording();
            }
        });
    }
    
    // 停止录音按钮
    const stopButton = document.getElementById('stopButton');
    if (stopButton) {
        stopButton.addEventListener('click', () => {
            if (window.audio) {
                window.audio.stopRecording();
            }
        });
    }
    
    // 回车发送消息
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                window.websocketManager.sendTextMessage();
            }
        });
    }
    
    // NFC测试相关
    const sendNfcButton = document.getElementById('sendNfcButton');
    if (sendNfcButton) {
        sendNfcButton.addEventListener('click', sendNfcCardMessage);
    }
    
    const nfcCardIdInput = document.getElementById('nfcCardId');
    if (nfcCardIdInput) {
        nfcCardIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendNfcCardMessage();
            }
        });
    }
}

// 发送NFC卡片消息
function sendNfcCardMessage() {
    const nfcCardIdInput = document.getElementById('nfcCardId');
    const cardId = nfcCardIdInput.value.trim();
    
    if (cardId === '' || !window.websocketManager.isConnected()) {
        utils.log('错误：请输入卡片ID且确保已连接服务器', 'error');
        return;
    }

    try {
        const nfcMessage = {
            type: 'nfc',
            card_id: cardId,
            timestamp: Date.now()
        };

        utils.log(`发送NFC卡片: ${cardId}`, 'info');
        window.websocketManager.sendBinaryData(JSON.stringify(nfcMessage));
        
        addMessage(`NFC卡片: ${cardId}`, true);
        nfcCardIdInput.value = '';
    } catch (error) {
        utils.log(`发送NFC消息失败: ${error.message}`, 'error');
    }
}

// 页面初始化
function initializePage() {
    // 初始化Opus库检查
    utils.checkOpusLoaded();
    
    // 初始化可视化器
    initVisualizer();
    
    // 初始化配置面板
    window.config.initConfigPanel();
    
    // 初始化标签页
    window.config.initTabs();
    
    // 初始化连接状态管理
    window.websocketManager.connectionStatus.init();
    
    // 初始化事件监听器
    initEventListeners();
    
    // 清理旧的UI元素
    cleanupUI();
    
    utils.log('页面初始化完成', 'success');
}

// 测试OTA连接
async function testOTAConnection() {
    try {
        const config = window.config.getConfig();
        if (!window.config.validateConfig(config)) {
            return;
        }
        
        utils.log('开始测试OTA连接...', 'info');
        await window.websocketManager.checkOTAStatus(config);
        utils.log('OTA连接测试完成', 'info');
        
    } catch (error) {
        utils.log(`OTA测试失败: ${error.message}`, 'error');
    }
}

// 重置设备配置
function resetDevice() {
    if (confirm('确定要重置设备配置吗？这将清除所有保存的设备信息，包括MAC地址、设备名称等。')) {
        try {
            // 断开连接
            if (window.websocketManager.isConnected()) {
                window.websocketManager.disconnectFromServer();
            }
            
            // 清除设备配置
            window.config.clearDeviceConfig();
            
            // 清除URL配置
            localStorage.removeItem('wsUrl');
            localStorage.removeItem('otaUrl');
            
            // 重置输入框
            const serverUrlInput = document.getElementById('serverUrl');
            const otaUrlInput = document.getElementById('otaUrl');
            
            if (serverUrlInput) {
                serverUrlInput.value = 'ws://127.0.0.1:8000/xiaozhi/v1/';
            }
            if (otaUrlInput) {
                otaUrlInput.value = 'http://127.0.0.1:8002/xiaozhi/ota/';
            }
            
            // 显示成功消息
            showConnectionStatus('设备配置已重置，页面将刷新', 'success');
            
            // 2秒后刷新页面
            setTimeout(() => {
                window.location.reload();
            }, 2000);
            
        } catch (error) {
            utils.log(`重置设备失败: ${error.message}`, 'error');
        }
    }
}

// 导出到全局
window.ui = {
    addMessage,
    initVisualizer,
    drawVisualizer,
    updateRecordButtonState,
    showConnectionStatus,
    cleanupUI,
    initEventListeners,
    initializePage,
    sendNfcCardMessage,
    testOTAConnection,
    resetDevice
};