// UI controller module
import { loadConfig, saveConfig } from '../config/manager.js?v=0127';
import { getAudioPlayer } from '../core/audio/player.js?v=0127';
import { getAudioRecorder } from '../core/audio/recorder.js?v=0127';
import { getWebSocketHandler } from '../core/network/websocket.js?v=0127';

// UI controller class
class UIController {
    constructor() {
        this.isEditing = false;
        this.visualizerCanvas = null;
        this.visualizerContext = null;
        this.audioStatsTimer = null;
        this.currentBackgroundIndex = 0;
        this.backgroundImages = ['1.png', '2.png', '3.png'];

        // Bind methods
        this.init = this.init.bind(this);
        this.initEventListeners = this.initEventListeners.bind(this);
        this.updateDialButton = this.updateDialButton.bind(this);
        this.addChatMessage = this.addChatMessage.bind(this);
        this.switchBackground = this.switchBackground.bind(this);
        this.showModal = this.showModal.bind(this);
        this.hideModal = this.hideModal.bind(this);
        this.switchTab = this.switchTab.bind(this);
    }

    // Initialize
    init() {
        console.log('UIController init started');

        this.visualizerCanvas = document.getElementById('audioVisualizer');
        if (this.visualizerCanvas) {
            this.visualizerContext = this.visualizerCanvas.getContext('2d');
            this.initVisualizer();
        }

        // Check if connect button exists during initialization
        const connectBtn = document.getElementById('connectBtn');
        console.log('connectBtn during init:', connectBtn);

        this.initEventListeners();
        this.startAudioStatsMonitor();
        loadConfig();

        // Register recording callback
        const audioRecorder = getAudioRecorder();
        audioRecorder.onRecordingStart = (seconds) => {
            this.updateRecordButtonState(true, seconds);
        };

        // Initialize status display
        this.updateConnectionUI(false);
        this.updateDialButton(false);

        // Initialize microphone selector
        this.initMicrophoneSelector();

        console.log('UIController init completed');
    }

    // Initialize visualizer
    initVisualizer() {
        if (this.visualizerCanvas) {
            this.visualizerCanvas.width = this.visualizerCanvas.clientWidth;
            this.visualizerCanvas.height = this.visualizerCanvas.clientHeight;
            this.visualizerContext.fillStyle = '#fafafa';
            this.visualizerContext.fillRect(0, 0, this.visualizerCanvas.width, this.visualizerCanvas.height);
        }
    }

    // Initialize event listeners
    initEventListeners() {
        // Settings button
        const settingsBtn = document.getElementById('settingsBtn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                this.showModal('settingsModal');
                // Refresh mic list when opening settings
                this.enumerateMicrophones();
            });
        }

        // Background switch button
        const backgroundBtn = document.getElementById('backgroundBtn');
        if (backgroundBtn) {
            backgroundBtn.addEventListener('click', this.switchBackground);
        }

        // Dial button
        const dialBtn = document.getElementById('dialBtn');
        if (dialBtn) {
            dialBtn.addEventListener('click', () => {
                const wsHandler = getWebSocketHandler();
                const isConnected = wsHandler.isConnected();

                if (isConnected) {
                    wsHandler.disconnect();
                    this.updateDialButton(false);
                    this.addChatMessage('Disconnected, see you next time~😊', false);
                } else {
                    // Check if OTA URL is filled
                    const otaUrlInput = document.getElementById('otaUrl');
                    if (!otaUrlInput || !otaUrlInput.value.trim()) {
                        // If OTA URL is not filled, show settings modal and switch to device tab
                        this.showModal('settingsModal');
                        this.switchTab('device');
                        this.addChatMessage('Please fill in OTA server URL', false);
                        return;
                    }

                    // Start connection process
                    this.handleConnect();
                }
            });
        }

        // Record button
        const recordBtn = document.getElementById('recordBtn');
        if (recordBtn) {
            recordBtn.addEventListener('click', () => {
                const audioRecorder = getAudioRecorder();
                if (audioRecorder.isRecording) {
                    audioRecorder.stop();
                    // Restore record button to normal state
                    recordBtn.classList.remove('recording');
                    recordBtn.querySelector('.btn-text').textContent = '录音';
                } else {
                    // Update button state to recording
                    recordBtn.classList.add('recording');
                    recordBtn.querySelector('.btn-text').textContent = '录音中';

                    // Start recording, update button state after delay
                    setTimeout(() => {
                        audioRecorder.start();
                    }, 100);
                }
            });
        }

        // Chat input event listener
        const chatIpt = document.getElementById('chatIpt');
        if (chatIpt) {
            const wsHandler = getWebSocketHandler();
            chatIpt.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    if (e.target.value) {
                        wsHandler.sendTextMessage(e.target.value);
                        e.target.value = '';
                        return;
                    }
                }
            });
        }

        // Close button
        const closeButtons = document.querySelectorAll('.close-btn');
        closeButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const modal = e.target.closest('.modal');
                if (modal) {
                    if (modal.id === 'settingsModal') {
                        saveConfig();
                    }
                    this.hideModal(modal.id);
                }
            });
        });

        // Settings tab switch
        const tabBtns = document.querySelectorAll('.tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });

        // Click modal background to close
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    if (modal.id === 'settingsModal') {
                        saveConfig();
                    }
                    this.hideModal(modal.id);
                }
            });
        });

        // Add MCP tool button
        const addMCPToolBtn = document.getElementById('addMCPToolBtn');
        if (addMCPToolBtn) {
            addMCPToolBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.addMCPTool();
            });
        }

        // Connect button and send button are not removed, can be added to dial button later
    }

    // Update connection status UI
    updateConnectionUI(isConnected) {
        const connectionStatus = document.getElementById('connectionStatus');
        const statusDot = document.querySelector('.status-dot');

        if (connectionStatus) {
            if (isConnected) {
                connectionStatus.textContent = '已连接';
                if (statusDot) {
                    statusDot.className = 'status-dot status-connected';
                }
            } else {
                connectionStatus.textContent = '离线';
                if (statusDot) {
                    statusDot.className = 'status-dot status-disconnected';
                }
            }
        }
    }

    // Update dial button state
    updateDialButton(isConnected) {
        const dialBtn = document.getElementById('dialBtn');
        const recordBtn = document.getElementById('recordBtn');

        if (dialBtn) {
            if (isConnected) {
                dialBtn.classList.add('dial-active');
                dialBtn.querySelector('.btn-text').textContent = '挂断';
                // Update dial button icon to hang up icon
                dialBtn.querySelector('svg').innerHTML = `
                    <path d="M12,9C10.4,9 9,10.4 9,12C9,13.6 10.4,15 12,15C13.6,15 15,13.6 15,12C15,10.4 13.6,9 12,9M12,17C9.2,17 7,14.8 7,12C7,9.2 9.2,7 12,7C14.8,7 17,9.2 17,12C17,14.8 14.8,17 12,17M12,4.5C7,4.5 2.7,7.6 1,12C2.7,16.4 7,19.5 12,19.5C17,19.5 21.3,16.4 23,12C21.3,7.6 17,4.5 12,4.5Z"/>
                `;
            } else {
                dialBtn.classList.remove('dial-active');
                dialBtn.querySelector('.btn-text').textContent = '拨号';
                // Restore dial button icon
                dialBtn.querySelector('svg').innerHTML = `
                    <path d="M6.62,10.79C8.06,13.62 10.38,15.94 13.21,17.38L15.41,15.18C15.69,14.9 16.08,14.82 16.43,14.93C17.55,15.3 18.75,15.5 20,15.5A1,1 0 0,1 21,16.5V20A1,1 0 0,1 20,21A17,17 0 0,1 3,4A1,1 0 0,1 4,3H7.5A1,1 0 0,1 8.5,4C8.5,5.25 8.7,6.45 9.07,7.57C9.18,7.92 9.1,8.31 8.82,8.59L6.62,10.79Z"/>
                `;
            }
        }

        // Update record button state
        if (recordBtn) {
            const microphoneAvailable = window.microphoneAvailable !== false;
            if (isConnected && microphoneAvailable) {
                recordBtn.disabled = false;
                recordBtn.title = '开始录音';
                // Restore record button to normal state
                recordBtn.querySelector('.btn-text').textContent = '录音';
                recordBtn.classList.remove('recording');
            } else {
                recordBtn.disabled = true;
                if (!microphoneAvailable) {
                    recordBtn.title = window.isHttpNonLocalhost ? '当前由于是http访问，无法录音，只能用文字交互' : '麦克风不可用';
                } else {
                    recordBtn.title = '请先连接服务器';
                }
                // Restore record button to normal state
                recordBtn.querySelector('.btn-text').textContent = '录音';
                recordBtn.classList.remove('recording');
            }
        }
    }

    // Update record button state
    updateRecordButtonState(isRecording, seconds = 0) {
        const recordBtn = document.getElementById('recordBtn');
        if (recordBtn) {
            if (isRecording) {
                recordBtn.querySelector('.btn-text').textContent = `录音中`;
                recordBtn.classList.add('recording');
            } else {
                recordBtn.querySelector('.btn-text').textContent = '录音';
                recordBtn.classList.remove('recording');
            }
            // Only enable button when microphone is available
            recordBtn.disabled = window.microphoneAvailable === false;
        }
    }

    /**
     * Update microphone availability state
     * @param {boolean} isAvailable - Whether microphone is available
     * @param {boolean} isHttpNonLocalhost - Whether it is HTTP non-localhost access
     */
    updateMicrophoneAvailability(isAvailable, isHttpNonLocalhost) {
        const recordBtn = document.getElementById('recordBtn');
        if (!recordBtn) return;
        if (!isAvailable) {
            // Disable record button
            recordBtn.disabled = true;
            // Update button text and title
            recordBtn.querySelector('.btn-text').textContent = '录音';
            recordBtn.title = isHttpNonLocalhost ? '当前由于是http访问，无法录音，只能用文字交互' : '麦克风不可用';

        } else {
            // If connected, enable record button
            const wsHandler = getWebSocketHandler();
            if (wsHandler && wsHandler.isConnected()) {
                recordBtn.disabled = false;
                recordBtn.title = '开始录音';
            }
        }
    }

    // Add chat message
    addChatMessage(content, isUser = false) {
        const chatStream = document.getElementById('chatStream');
        if (!chatStream) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user' : 'ai'}`;
        messageDiv.innerHTML = `<div class="message-bubble">${content}</div>`;
        chatStream.appendChild(messageDiv);

        // Scroll to bottom
        chatStream.scrollTop = chatStream.scrollHeight;
    }

    // Switch background
    switchBackground() {
        this.currentBackgroundIndex = (this.currentBackgroundIndex + 1) % this.backgroundImages.length;
        const backgroundContainer = document.querySelector('.background-container');
        if (backgroundContainer) {
            backgroundContainer.style.backgroundImage = `url('./images/${this.backgroundImages[this.currentBackgroundIndex]}')`;
        }
    }

    // Show modal
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'flex';
        }
    }

    // Hide modal
    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
        }
    }

    // Switch tab
    switchTab(tabName) {
        // Remove active class from all tabs
        const tabBtns = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        tabBtns.forEach(btn => btn.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));

        // Activate selected tab
        const activeTabBtn = document.querySelector(`[data-tab="${tabName}"]`);
        const activeTabContent = document.getElementById(`${tabName}Tab`);

        if (activeTabBtn && activeTabContent) {
            activeTabBtn.classList.add('active');
            activeTabContent.classList.add('active');
        }
    }

    // Start AI chat session after connection
    startAIChatSession() {
        this.addChatMessage('连接成功，开始聊天吧~😊', false);
        // Check microphone availability and show error messages if needed
        if (!window.microphoneAvailable) {
            if (window.isHttpNonLocalhost) {
                this.addChatMessage('⚠️ 当前由于是http访问，无法录音，只能用文字交互', false);
            } else {
                this.addChatMessage('⚠️ 麦克风不可用，请检查权限设置，只能用文字交互', false);
            }
        }
        // Start recording only if microphone is available
        if (window.microphoneAvailable) {
            const recordBtn = document.getElementById('recordBtn');
            if (recordBtn) {
                recordBtn.click();
            }
        }
    }

    // Handle connect button click
    async handleConnect() {
        console.log('handleConnect called');

        // Switch to device settings tab
        this.switchTab('device');

        // Wait for DOM update
        await new Promise(resolve => setTimeout(resolve, 50));

        const otaUrlInput = document.getElementById('otaUrl');

        console.log('otaUrl element:', otaUrlInput);

        if (!otaUrlInput || !otaUrlInput.value) {
            this.addChatMessage('请输入OTA服务器地址', false);
            return;
        }

        const otaUrl = otaUrlInput.value;
        console.log('otaUrl value:', otaUrl);

        // Update dial button state to connecting
        const dialBtn = document.getElementById('dialBtn');
        if (dialBtn) {
            dialBtn.classList.add('dial-active');
            dialBtn.querySelector('.btn-text').textContent = '连接中...';
            dialBtn.disabled = true;
        }

        // Show connecting message
        this.addChatMessage('正在连接服务器...', false);

        const chatIpt = document.getElementById('chatIpt');
        if (chatIpt) {
            chatIpt.style.display = 'flex';
        }

        try {

            // Get WebSocket handler instance
            const wsHandler = getWebSocketHandler();

            // Register connection state callback BEFORE connecting
            wsHandler.onConnectionStateChange = (isConnected) => {
                this.updateConnectionUI(isConnected);
                this.updateDialButton(isConnected);
            };

            // Register chat message callback BEFORE connecting
            wsHandler.onChatMessage = (text, isUser) => {
                this.addChatMessage(text, isUser);
            };

            // Register record button state callback BEFORE connecting
            wsHandler.onRecordButtonStateChange = (isRecording) => {
                const recordBtn = document.getElementById('recordBtn');
                if (recordBtn) {
                    if (isRecording) {
                        recordBtn.classList.add('recording');
                        recordBtn.querySelector('.btn-text').textContent = '录音中';
                    } else {
                        recordBtn.classList.remove('recording');
                        recordBtn.querySelector('.btn-text').textContent = '录音';
                    }
                }
            };

            const isConnected = await wsHandler.connect();

            if (isConnected) {
                // Check microphone availability (check again after connection)
                const { checkMicrophoneAvailability } = await import('../core/audio/recorder.js?v=0127');
                const micAvailable = await checkMicrophoneAvailability();

                if (!micAvailable) {
                    const isHttp = window.isHttpNonLocalhost;
                    if (isHttp) {
                        this.addChatMessage('⚠️ 当前由于是http访问，无法录音，只能用文字交互', false);
                    }
                    // Update global state
                    window.microphoneAvailable = false;
                }

                // Update dial button state
                const dialBtn = document.getElementById('dialBtn');
                if (dialBtn) {
                    dialBtn.disabled = false;
                    dialBtn.querySelector('.btn-text').textContent = '挂断';
                    dialBtn.classList.add('dial-active');
                }

                this.hideModal('settingsModal');

            } else {
                throw new Error('OTA连接失败');
            }
        } catch (error) {
            console.error('Connection error details:', {
                message: error.message,
                stack: error.stack,
                name: error.name
            });

            // Show error message
            const errorMessage = error.message.includes('Cannot set properties of null')
                ? '连接失败：请检查设备连接'
                : `连接失败: ${error.message}`;

            this.addChatMessage(errorMessage, false);

            // Restore dial button state
            const dialBtn = document.getElementById('dialBtn');
            if (dialBtn) {
                dialBtn.disabled = false;
                dialBtn.querySelector('.btn-text').textContent = '拨号';
                dialBtn.classList.remove('dial-active');
                console.log('Dial button state restored successfully');
            }
        }
    }

    // Add MCP tool
    addMCPTool() {
        const mcpToolsList = document.getElementById('mcpToolsList');
        if (!mcpToolsList) return;

        const toolId = `mcp-tool-${Date.now()}`;
        const toolDiv = document.createElement('div');
        toolDiv.className = 'properties-container';
        toolDiv.innerHTML = `
            <div class="property-item">
                <input type="text" placeholder="工具名称" value="新工具">
                <input type="text" placeholder="工具描述" value="工具描述">
                <button class="remove-property" onclick="uiController.removeMCPTool('${toolId}')">删除</button>
            </div>
        `;

        mcpToolsList.appendChild(toolDiv);
    }

    // Remove MCP tool
    removeMCPTool(toolId) {
        const toolElement = document.getElementById(toolId);
        if (toolElement) {
            toolElement.remove();
        }
    }

    // Update audio statistics display
    updateAudioStats() {
        const audioPlayer = getAudioPlayer();
        if (!audioPlayer) return;

        const stats = audioPlayer.getAudioStats();
        // Here can add audio statistics UI update logic
    }

    // Start audio statistics monitor
    startAudioStatsMonitor() {
        // Update audio statistics every 100ms
        this.audioStatsTimer = setInterval(() => {
            this.updateAudioStats();
        }, 100);
    }

    // Stop audio statistics monitor
    stopAudioStatsMonitor() {
        if (this.audioStatsTimer) {
            clearInterval(this.audioStatsTimer);
            this.audioStatsTimer = null;
        }
    }

    // Draw audio visualizer waveform
    drawVisualizer(dataArray) {
        if (!this.visualizerContext || !this.visualizerCanvas) return;

        this.visualizerContext.fillStyle = '#fafafa';
        this.visualizerContext.fillRect(0, 0, this.visualizerCanvas.width, this.visualizerCanvas.height);

        const barWidth = (this.visualizerCanvas.width / dataArray.length) * 2.5;
        let barHeight;
        let x = 0;

        for (let i = 0; i < dataArray.length; i++) {
            barHeight = dataArray[i] / 2;

            // Create gradient color: from purple to blue to green
            const gradient = this.visualizerContext.createLinearGradient(0, 0, 0, this.visualizerCanvas.height);
            gradient.addColorStop(0, '#8e44ad');
            gradient.addColorStop(0.5, '#3498db');
            gradient.addColorStop(1, '#1abc9c');

            this.visualizerContext.fillStyle = gradient;
            this.visualizerContext.fillRect(x, this.visualizerCanvas.height - barHeight, barWidth, barHeight);
            x += barWidth + 1;
        }
    }

    // Update session status UI
    updateSessionStatus(isSpeaking) {
        // Here can add session status UI update logic
        // For example: update Live2D model's mouth movement status
    }

    // Update session emotion
    updateSessionEmotion(emoji) {
        // Here can add emotion update logic
        // For example: display emoji in status indicator
    }

    // Initialize microphone selector
    initMicrophoneSelector() {
        const micSelect = document.getElementById('micSelect');
        if (!micSelect) return;

        // Load saved selection
        const savedDeviceId = localStorage.getItem('selectedMicDeviceId');
        if (savedDeviceId) {
            const audioRecorder = getAudioRecorder();
            audioRecorder.setDeviceId(savedDeviceId);
        }

        // Handle selection change
        micSelect.addEventListener('change', (e) => {
            const deviceId = e.target.value;
            const audioRecorder = getAudioRecorder();
            audioRecorder.setDeviceId(deviceId);
            localStorage.setItem('selectedMicDeviceId', deviceId);
        });

        // Initial enumeration
        this.enumerateMicrophones();
    }

    // Enumerate available microphones
    async enumerateMicrophones() {
        const micSelect = document.getElementById('micSelect');
        if (!micSelect) return;

        try {
            // Request permission first (needed to get device labels)
            await navigator.mediaDevices.getUserMedia({ audio: true })
                .then(stream => stream.getTracks().forEach(t => t.stop()));

            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter(d => d.kind === 'audioinput');

            const savedDeviceId = localStorage.getItem('selectedMicDeviceId') || '';

            // Keep default option, clear the rest
            micSelect.innerHTML = '<option value="">默认麦克风</option>';

            audioInputs.forEach((device, index) => {
                const option = document.createElement('option');
                option.value = device.deviceId;
                option.textContent = device.label || `麦克风 ${index + 1}`;
                if (device.deviceId === savedDeviceId) {
                    option.selected = true;
                }
                micSelect.appendChild(option);
            });

            console.log(`Found ${audioInputs.length} microphone(s)`);
        } catch (err) {
            console.warn('Failed to enumerate microphones:', err.message);
        }
    }
}

// Create singleton instance
export const uiController = new UIController();

// Export class for module usage
export { UIController };
