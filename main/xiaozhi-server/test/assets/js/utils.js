// 工具函数模块

// 日志记录函数
function log(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logContainer = document.getElementById('logContainer');
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.textContent = `[${timestamp}] ${message}`;
    
    if (logContainer) {
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }
    
    console.log(`[${type.toUpperCase()}] ${message}`);
}

// 生成随机MAC地址
function generateRandomMac() {
    const chars = '0123456789ABCDEF';
    let mac = '';
    for (let i = 0; i < 12; i++) {
        if (i > 0 && i % 2 === 0) mac += ':';
        mac += chars[Math.floor(Math.random() * chars.length)];
    }
    return mac;
}

// 更新脚本状态显示
function updateScriptStatus(message, type) {
    const statusElement = document.getElementById('scriptStatus');
    if (statusElement) {
        statusElement.textContent = message;
        statusElement.className = `script-status ${type}`;
        statusElement.style.display = 'block';
        statusElement.style.width = 'auto';
    }
}

// 检查Opus库是否已加载
function checkOpusLoaded() {
    try {
        // 检查Module是否存在（本地库导出的全局变量）
        if (typeof Module === 'undefined') {
            throw new Error('Opus库未加载，Module对象不存在');
        }

        // 尝试先使用Module.instance（libopus.js最后一行导出方式）
        if (typeof Module.instance !== 'undefined' && typeof Module.instance._opus_decoder_get_size === 'function') {
            // 使用Module.instance对象替换全局Module对象
            window.ModuleInstance = Module.instance;
            log('Opus库加载成功（使用Module.instance）', 'success');
            updateScriptStatus('Opus库加载成功', 'success');

            // 3秒后隐藏状态
            const statusElement = document.getElementById('scriptStatus');
            if (statusElement) statusElement.style.display = 'none';
            return;
        }

        // 如果没有Module.instance，检查全局Module函数
        if (typeof Module._opus_decoder_get_size === 'function') {
            window.ModuleInstance = Module;
            log('Opus库加载成功（使用全局Module）', 'success');
            updateScriptStatus('Opus库加载成功', 'success');

            // 3秒后隐藏状态
            const statusElement = document.getElementById('scriptStatus');
            if (statusElement) statusElement.style.display = 'none';
            return;
        }

        throw new Error('Opus解码函数未找到，可能Module结构不正确');
    } catch (err) {
        log(`Opus库加载失败，请检查libopus.js文件是否存在且正确: ${err.message}`, 'error');
        updateScriptStatus('Opus库加载失败，请检查libopus.js文件是否存在且正确', 'error');
    }
}

// 全局变量和常量
const SAMPLE_RATE = 16000;     // 采样率
const CHANNELS = 1;            // 声道数
const FRAME_SIZE = 960;        // 帧大小
const BUFFER_THRESHOLD = 3;    // 缓冲包数量阈值
const MIN_AUDIO_DURATION = 0.1; // 最小音频长度(秒)

// 导出到全局
window.utils = {
    log,
    generateRandomMac,
    updateScriptStatus,
    checkOpusLoaded,
    SAMPLE_RATE,
    CHANNELS,
    FRAME_SIZE,
    BUFFER_THRESHOLD,
    MIN_AUDIO_DURATION
};