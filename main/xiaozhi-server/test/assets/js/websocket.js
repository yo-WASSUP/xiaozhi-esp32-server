// WebSocket连接模块

// 全局WebSocket变量
let websocket = null;

// 连接状态管理
const connectionStatus = {
    element: null,
    otaElement: null,
    
    init() {
        this.element = document.getElementById('connectionStatus');
        this.otaElement = document.getElementById('otaStatus');
    },
    
    updateWS(status, color) {
        if (this.element) {
            this.element.textContent = status;
            this.element.style.color = color;
        }
    },
    
    updateOTA(status, color) {
        if (this.otaElement) {
            this.otaElement.textContent = status;
            this.otaElement.style.color = color;
        }
    }
};

// 连接到WebSocket服务器
async function connectToServer() {
    const serverUrlInput = document.getElementById('serverUrl');
    const url = serverUrlInput.value.trim();
    if (url === '') return;

    try {
        // 获取并验证配置
        const config = window.config.getConfig();
        if (!window.config.validateConfig(config)) {
            return;
        }

        connectionStatus.updateWS('ws连接中', 'orange');
        
        // 保存URL到本地存储
        localStorage.setItem('wsUrl', url);

        // 先检查OTA状态
        await checkOTAStatus(config);

        // 创建URL对象用于添加参数
        const connUrl = new URL(url);
        
        // 添加认证参数
        connUrl.searchParams.append('device-id', config.deviceId);
        connUrl.searchParams.append('client-id', config.clientId);

        utils.log(`正在连接: ${connUrl.toString()}`, 'info');
        websocket = new WebSocket(connUrl.toString());

        // 设置接收二进制数据的类型为ArrayBuffer
        websocket.binaryType = 'arraybuffer';

        websocket.onopen = async () => {
            utils.log(`已连接到服务器: ${url}`, 'success');
            connectionStatus.updateWS('ws已连接', 'green');

            // 连接成功后发送hello消息
            await sendHelloMessage();

            // 更新UI状态
            updateConnectionUI(true);

            // 初始化音频
            const audioInitialized = await window.audio.initAudio();
            if (audioInitialized) {
                const recordButton = document.getElementById('recordButton');
                if (recordButton) recordButton.disabled = false;
            }
        };

        websocket.onclose = () => {
            utils.log('已断开连接', 'info');
            connectionStatus.updateWS('ws已断开', 'red');
            updateConnectionUI(false);
        };

        websocket.onerror = (error) => {
            utils.log(`WebSocket错误: ${error.message || '未知错误'}`, 'error');
            connectionStatus.updateWS('ws未连接', 'red');
        };

        websocket.onmessage = handleWebSocketMessage;

    } catch (error) {
        utils.log(`连接错误: ${error.message}`, 'error');
        connectionStatus.updateWS('ws未连接', 'red');
    }
}

// 断开WebSocket连接
function disconnectFromServer() {
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    updateConnectionUI(false);
}

// 更新连接相关的UI状态
function updateConnectionUI(connected) {
    const connectButton = document.getElementById('connectButton');
    const messageInput = document.getElementById('messageInput');
    const sendTextButton = document.getElementById('sendTextButton');
    const recordButton = document.getElementById('recordButton');
    const stopButton = document.getElementById('stopButton');

    if (connected) {
        connectButton.textContent = '断开';
        connectButton.removeEventListener('click', connectToServer);
        connectButton.addEventListener('click', disconnectFromServer);
        if (messageInput) messageInput.disabled = false;
        if (sendTextButton) sendTextButton.disabled = false;
    } else {
        connectButton.textContent = '连接';
        connectButton.removeEventListener('click', disconnectFromServer);
        connectButton.addEventListener('click', connectToServer);
        if (messageInput) messageInput.disabled = true;
        if (sendTextButton) sendTextButton.disabled = true;
        if (recordButton) recordButton.disabled = true;
        if (stopButton) stopButton.disabled = true;
    }
}

// 处理WebSocket消息
function handleWebSocketMessage(event) {
    try {
        // 检查是否为文本消息
        if (typeof event.data === 'string') {
            const message = JSON.parse(event.data);

            if (message.type === 'hello') {
                utils.log(`服务器回应：${JSON.stringify(message, null, 2)}`, 'success');
            } else if (message.type === 'tts') {
                handleTTSMessage(message);
            } else if (message.type === 'mcp') {
                handleMCPMessage(message);
            } else if (message.type === 'stt' || message.type === 'asr') {
                // 处理语音识别结果
                handleSTTMessage(message);
            } else if (message.type === 'listen') {
                // 处理监听状态消息
                handleListenMessage(message);
            } else if (message.type === 'text' || message.text) {
                // 处理包含文本内容的消息
                handleTextMessage(message);
            } else {
                utils.log(`收到消息: ${JSON.stringify(message)}`, 'info');
            }
        } else if (event.data instanceof ArrayBuffer) {
            // 处理二进制音频数据
            handleAudioData(event.data);
        }
    } catch (error) {
        utils.log(`消息处理错误: ${error.message}`, 'error');
    }
}

// 处理TTS消息
function handleTTSMessage(message) {
    if (message.state === 'start') {
        utils.log('服务器开始发送语音', 'info');
    } else if (message.state === 'sentence_start') {
        utils.log(`服务器发送语音段: ${message.text}`, 'info');
        // 添加文本到会话记录
        if (message.text) {
            window.ui.addMessage(message.text);
        }
        
        // 累积消息用于ROS2命令检测
        if (window.ros2) {
            window.ros2.addToMessageBuffer(message.text);
        }
    } else if (message.state === 'sentence_end') {
        utils.log(`语音段结束: ${message.text}`, 'info');
    } else if (message.state === 'stop') {
        utils.log('服务器语音传输结束', 'info');
    }
}

// 处理语音识别结果消息
function handleSTTMessage(message) {
    utils.log(`收到语音识别结果: ${JSON.stringify(message)}`, 'info');
    
    if (message.text) {
        utils.log(`识别文本: ${message.text}`, 'success');
        // 添加识别结果到会话记录
        window.ui.addMessage(`[识别] ${message.text}`, true);
        
        // 检查ROS2命令
        if (window.ros2) {
            window.ros2.checkAndExecuteROS2Command(message.text);
        }
    }
    
    if (message.state === 'final' || message.is_final) {
        utils.log('语音识别完成', 'info');
    }
}

// 处理监听状态消息
function handleListenMessage(message) {
    utils.log(`监听状态: ${JSON.stringify(message)}`, 'info');
    
    if (message.state === 'listening') {
        utils.log('服务器开始监听语音', 'info');
    } else if (message.state === 'processing') {
        utils.log('服务器正在处理语音', 'info');
    } else if (message.state === 'done') {
        utils.log('语音处理完成', 'info');
    }
    
    // 如果包含识别文本
    if (message.text) {
        utils.log(`监听到文本: ${message.text}`, 'success');
        window.ui.addMessage(`[监听] ${message.text}`, true);
        
        // 检查ROS2命令
        if (window.ros2) {
            window.ros2.checkAndExecuteROS2Command(message.text);
        }
    }
}

// 处理文本消息
function handleTextMessage(message) {
    utils.log(`收到文本消息: ${JSON.stringify(message)}`, 'info');
    
    if (message.text) {
        // 添加到会话记录
        window.ui.addMessage(message.text);
        
        // 检查ROS2命令
        if (window.ros2) {
            window.ros2.checkAndExecuteROS2Command(message.text);
        }
    }
}

// 处理MCP消息
function handleMCPMessage(message) {
    const payload = message.payload;
    if (payload) {
        // 模拟小智客户端行为
        if (payload.method === 'tools/list') {
            const replayMessage = JSON.stringify({
                "session_id": "",
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "self.get_device_status",
                                "description": "Provides the real-time information of the device",
                                "inputSchema": {"type": "object", "properties": {}}
                            }
                        ]
                    }
                }
            });
            websocket.send(replayMessage);
            utils.log(`回复MCP消息: ${replayMessage}`, 'info');
        } else if (payload.method === 'tools/call') {
            const replayMessage = JSON.stringify({
                "session_id": "9f261599",
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "result": {
                        "content": [{"type": "text", "text": "true"}],
                        "isError": false
                    }
                }
            });
            websocket.send(replayMessage);
            utils.log(`回复MCP消息: ${replayMessage}`, 'info');
        }
    }
}

// 处理音频数据
function handleAudioData(arrayBuffer) {
    try {
        if (window.audio && window.audio.handleIncomingAudio) {
            window.audio.handleIncomingAudio(arrayBuffer);
        }
    } catch (error) {
        utils.log(`音频数据处理错误: ${error.message}`, 'error');
    }
}

// 发送hello握手消息
async function sendHelloMessage() {
    if (!websocket || websocket.readyState !== WebSocket.OPEN) return;

    try {
        const config = window.config.getConfig();

        // 设置设备信息
        const helloMessage = {
            type: 'hello',
            device_id: config.deviceId,
            device_name: config.deviceName,
            device_mac: config.deviceMac,
            client_id: config.clientId,
            token: config.token,
            version: "0.0.1",
            capabilities: {
                audio: true,
                video: false,
                text: true
            }
        };

        utils.log(`发送hello消息: ${JSON.stringify(helloMessage, null, 2)}`, 'info');
        websocket.send(JSON.stringify(helloMessage));
    } catch (error) {
        utils.log(`发送hello消息失败: ${error.message}`, 'error');
    }
}

// 发送文本消息
function sendTextMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    if (message === '' || !websocket || websocket.readyState !== WebSocket.OPEN) return;

    // 清理音频缓冲
    if (window.audio) {
        window.audio.clearAudioBuffers();
    }

    try {
        // 发送listen消息
        const listenMessage = {
            type: 'listen',
            mode: 'manual',
            state: 'detect',
            text: message
        };

        utils.log(`发送消息: ${message}`, 'info');
        websocket.send(JSON.stringify(listenMessage));
        
        // 添加到会话记录
        window.ui.addMessage(message, true);
        messageInput.value = '';
    } catch (error) {
        utils.log(`发送消息失败: ${error.message}`, 'error');
    }
}

// 发送文本数据
function sendTextData(data) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        try {
            websocket.send(data);
        } catch (error) {
            utils.log(`发送文本数据失败: ${error.message}`, 'error');
        }
    }
}

// 发送二进制数据
function sendBinaryData(data) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        try {
            websocket.send(data);
        } catch (error) {
            utils.log(`发送二进制数据失败: ${error.message}`, 'error');
        }
    }
}

// 检查OTA状态
async function checkOTAStatus(config) {
    utils.log('正在检查OTA状态...', 'info');
    const otaUrlInput = document.getElementById('otaUrl');
    const otaUrl = otaUrlInput.value.trim();
    
    // 保存到本地存储
    localStorage.setItem('otaUrl', otaUrl);
    
    try {
        const otaResponse = await fetch(otaUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Device-Id': config.deviceId,
                'Client-Id': config.clientId
            },
            body: JSON.stringify({
                "version": 1,
                "uuid": config.deviceId,
                "application": {
                    "name": "xiaozhi-web-test",
                    "version": "1.0.0",
                    "compile_time": new Date().toISOString().replace('T', ' ').substring(0, 19),
                    "idf_version": "4.4.3",
                    "elf_sha256": "1234567890abcdef1234567890abcdef1234567890abcdef"
                },
                "ota": {
                    "label": "xiaozhi-web-test"
                },
                "board": {
                    "type": "xiaozhi-web-test",
                    "ssid": "xiaozhi-web-test",
                    "rssi": -50,
                    "channel": 6,
                    "ip": "192.168.1.100",
                    "mac": config.deviceMac
                },
                "flash_size": 4194304,
                "minimum_free_heap_size": 100000,
                "mac_address": config.deviceMac,
                "chip_model_name": "ESP32",
                "chip_info": {
                    "model": 1,
                    "cores": 2,
                    "revision": 1,
                    "features": 32
                },
                "partition_table": [
                    {
                        "label": "app0",
                        "type": 0,
                        "subtype": 16,
                        "address": 65536,
                        "size": 1572864
                    }
                ]
            })
        });

        if (!otaResponse.ok) {
            throw new Error(`OTA检查失败: ${otaResponse.status} ${otaResponse.statusText}`);
        }

        const otaResult = await otaResponse.json();
        utils.log(`OTA检查结果: ${JSON.stringify(otaResult)}`, 'info');

        utils.log('OTA检查通过', 'success');
        connectionStatus.updateOTA('ota已连接', 'green');
        
    } catch (error) {
        utils.log(`OTA检查错误: ${error.message}`, 'error');
        connectionStatus.updateOTA('ota未连接', 'red');
        // OTA检查失败不阻止WebSocket连接，只是警告
        utils.log('OTA检查失败，但继续尝试WebSocket连接', 'warning');
    }
}

// 导出到全局
window.websocketManager = {
    connectToServer,
    disconnectFromServer,
    sendTextMessage,
    sendTextData,
    sendBinaryData,
    sendHelloMessage,
    connectionStatus,
    checkOTAStatus,
    isConnected: () => websocket && websocket.readyState === WebSocket.OPEN
};