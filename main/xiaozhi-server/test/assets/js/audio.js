// 音频处理模块 - 完整版本

// 音频相关全局变量
let mediaRecorder = null;
let audioContext = null;
let analyser = null;
let audioChunks = [];
let isRecording = false;
let audioBufferQueue = [];
let isAudioBuffering = false;
let isAudioPlaying = false;
let opusDecoder = null;
let visualizationRequest = null;
let streamingContext = null;

// 初始化音频
async function initAudio() {
    try {
        // 请求麦克风权限
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: utils.SAMPLE_RATE,
                channelCount: utils.CHANNELS,
                echoCancellation: true,
                noiseSuppression: true
            } 
        });

        // 创建音频上下文
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: utils.SAMPLE_RATE
        });

        // 创建分析器
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;

        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);

        // 创建MediaRecorder
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });

        setupMediaRecorderEvents();

        utils.log('音频初始化成功', 'success');
        return true;

    } catch (error) {
        utils.log(`音频初始化失败: ${error.message}`, 'error');
        return false;
    }
}

// 设置MediaRecorder事件
function setupMediaRecorderEvents() {
    mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
            audioChunks.push(event.data);
            
            // 如果WebSocket已连接，直接发送数据
            if (window.websocketManager.isConnected()) {
                // 将Blob转换为ArrayBuffer再发送
                event.data.arrayBuffer().then(buffer => {
                    window.websocketManager.sendBinaryData(buffer);
                    utils.log(`发送音频数据，大小：${buffer.byteLength}字节`, 'debug');
                });
            }
        }
    };

    mediaRecorder.onstart = () => {
        utils.log('MediaRecorder开始录音', 'info');
        isRecording = true;
        window.ui.updateRecordButtonState(true);
        
        // 开始可视化
        if (analyser) {
            const dataArray = new Uint8Array(analyser.frequencyBinCount);
            drawVisualization(dataArray);
        }
    };

    mediaRecorder.onstop = () => {
        utils.log('MediaRecorder停止录音', 'info');
        isRecording = false;
        window.ui.updateRecordButtonState(false);
        
        // 停止可视化
        if (visualizationRequest) {
            cancelAnimationFrame(visualizationRequest);
            visualizationRequest = null;
        }
    };
}

// 绘制音频可视化
function drawVisualization(dataArray) {
    if (!isRecording) return;
    
    visualizationRequest = requestAnimationFrame(() => drawVisualization(dataArray));
    window.ui.drawVisualizer(dataArray, isRecording);
}

// 开始录音
async function startRecording() {
    if (!mediaRecorder || isRecording) return;

    try {
        // 清理音频缓冲
        clearAudioBuffers();
        
        // 发送录音开始消息
        if (window.websocketManager.isConnected()) {
            const listenMessage = {
                type: 'listen',
                mode: 'manual',
                state: 'start'
            };

            utils.log(`发送录音开始消息: ${JSON.stringify(listenMessage)}`, 'info');
            window.websocketManager.sendBinaryData(JSON.stringify(listenMessage));
        }

        // 开始录音，设置较小的时间片以获得更好的实时性
        mediaRecorder.start(100); // 每100ms产生一个数据块
        
        utils.log('开始录音', 'info');

    } catch (error) {
        utils.log(`录音错误: ${error.message}`, 'error');
    }
}

// 停止录音
async function stopRecording() {
    if (!mediaRecorder || !isRecording) return;

    try {
        mediaRecorder.stop();
        
        // 发送录音结束消息
        if (window.websocketManager.isConnected()) {
            // 发送空的音频帧作为结束标志
            const emptyFrame = new Uint8Array(0);
            window.websocketManager.sendBinaryData(emptyFrame);

            // 发送监听结束消息
            const stopMessage = {
                type: 'listen',
                mode: 'manual',
                state: 'stop'
            };

            utils.log(`发送录音结束消息: ${JSON.stringify(stopMessage)}`, 'info');
            window.websocketManager.sendBinaryData(JSON.stringify(stopMessage));
        }

        utils.log('停止录音', 'info');

    } catch (error) {
        utils.log(`停止录音错误: ${error.message}`, 'error');
    }
}

// 处理传入的音频数据 - 完整版本
async function handleIncomingAudio(arrayBuffer) {
    try {
        utils.log(`收到音频数据: ${arrayBuffer.byteLength} 字节`, 'debug');
        
        // 创建Uint8Array用于处理
        const opusData = new Uint8Array(arrayBuffer);

        if (opusData.length > 0) {
            // 将数据添加到缓冲队列
            audioBufferQueue.push(opusData);

            // 如果收到的是第一个音频包，开始缓冲过程
            if (audioBufferQueue.length === 1 && !isAudioBuffering && !isAudioPlaying) {
                startAudioBuffering();
            }
        } else {
            utils.log('收到空音频数据帧，可能是结束标志', 'warning');

            // 如果缓冲队列中有数据且没有在播放，立即开始播放
            if (audioBufferQueue.length > 0 && !isAudioPlaying) {
                playBufferedAudio();
            }

            // 如果正在播放，发送结束信号
            if (isAudioPlaying && streamingContext) {
                streamingContext.endOfStream = true;
            }
        }
        
    } catch (error) {
        utils.log(`处理音频数据失败: ${error.message}`, 'error');
    }
}

// 开始音频缓冲
function startAudioBuffering() {
    if (isAudioBuffering || isAudioPlaying) return;

    isAudioBuffering = true;
    utils.log("开始音频缓冲...", 'info');

    // 先尝试初始化解码器，以便在播放时已准备好
    initOpusDecoder().catch(error => {
        utils.log(`预初始化Opus解码器失败: ${error.message}`, 'warning');
        // 继续缓冲，我们会在播放时再次尝试初始化
    });

    // 设置超时，如果在一定时间内没有收集到足够的音频包，就开始播放
    setTimeout(() => {
        if (isAudioBuffering && audioBufferQueue.length > 0) {
            utils.log(`缓冲超时，当前缓冲包数: ${audioBufferQueue.length}，开始播放`, 'info');
            playBufferedAudio();
        }
    }, 300); // 300ms超时

    // 监控缓冲进度
    const bufferCheckInterval = setInterval(() => {
        if (!isAudioBuffering) {
            clearInterval(bufferCheckInterval);
            return;
        }

        // 当累积了足够的音频包，开始播放
        if (audioBufferQueue.length >= utils.BUFFER_THRESHOLD) {
            clearInterval(bufferCheckInterval);
            utils.log(`已缓冲 ${audioBufferQueue.length} 个音频包，开始播放`, 'info');
            playBufferedAudio();
        }
    }, 50);
}

// 播放缓冲的音频 - 完整版本
function playBufferedAudio() {
    if (isAudioPlaying || audioBufferQueue.length === 0) return;

    isAudioPlaying = true;
    isAudioBuffering = false;

    // 确保Opus解码器已初始化
    const initDecoderAndPlay = async () => {
        try {
            // 确保音频上下文存在
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: utils.SAMPLE_RATE
                });
                utils.log('创建音频上下文，采样率: ' + utils.SAMPLE_RATE + 'Hz', 'debug');
            }

            // 确保解码器已初始化
            if (!opusDecoder) {
                utils.log('初始化Opus解码器...', 'info');
                try {
                    opusDecoder = await initOpusDecoder();
                    if (!opusDecoder) {
                        throw new Error('解码器初始化失败');
                    }
                    utils.log('Opus解码器初始化成功', 'success');
                } catch (error) {
                    utils.log('Opus解码器初始化失败: ' + error.message, 'error');
                    isAudioPlaying = false;
                    return;
                }
            }

            // 创建流式播放上下文
            if (!streamingContext) {
                streamingContext = {
                    queue: [],          // 已解码的PCM队列
                    playing: false,     // 是否正在播放
                    endOfStream: false, // 是否收到结束信号
                    source: null,       // 当前音频源
                    totalSamples: 0,    // 累积的总样本数
                    lastPlayTime: 0,    // 上次播放的时间戳

                    // 将Opus数据解码为PCM
                    decodeOpusFrames: async function (opusFrames) {
                        if (!opusDecoder) {
                            utils.log('Opus解码器未初始化，无法解码', 'error');
                            return;
                        }

                        let decodedSamples = [];

                        for (const frame of opusFrames) {
                            try {
                                // 使用Opus解码器解码
                                const frameData = opusDecoder.decode(frame);
                                if (frameData && frameData.length > 0) {
                                    // 转换为Float32
                                    const floatData = convertInt16ToFloat32(frameData);
                                    // 使用循环替代展开运算符
                                    for (let i = 0; i < floatData.length; i++) {
                                        decodedSamples.push(floatData[i]);
                                    }
                                }
                            } catch (error) {
                                utils.log("Opus解码失败: " + error.message, 'error');
                            }
                        }

                        if (decodedSamples.length > 0) {
                            // 使用循环替代展开运算符
                            for (let i = 0; i < decodedSamples.length; i++) {
                                this.queue.push(decodedSamples[i]);
                            }
                            this.totalSamples += decodedSamples.length;

                            // 如果累积了至少0.2秒的音频，开始播放
                            const minSamples = utils.SAMPLE_RATE * utils.MIN_AUDIO_DURATION;
                            if (!this.playing && this.queue.length >= minSamples) {
                                this.startPlaying();
                            }
                        }
                    },

                    // 开始播放队列中的音频
                    startPlaying: function () {
                        if (this.playing || this.queue.length === 0) return;

                        this.playing = true;
                        utils.log(`开始播放音频，队列长度: ${this.queue.length}`, 'info');

                        // 计算每次播放的样本数
                        const playDuration = 0.1; // 100ms
                        const samplesPerPlay = Math.floor(utils.SAMPLE_RATE * playDuration);
                        const samplesToPlay = Math.min(samplesPerPlay, this.queue.length);

                        if (samplesToPlay === 0) {
                            this.playing = false;
                            return;
                        }

                        // 从队列中取出样本
                        const samples = this.queue.splice(0, samplesToPlay);
                        
                        // 创建AudioBuffer
                        const buffer = audioContext.createBuffer(1, samples.length, utils.SAMPLE_RATE);
                        const channelData = buffer.getChannelData(0);
                        
                        for (let i = 0; i < samples.length; i++) {
                            channelData[i] = samples[i];
                        }

                        // 创建音频源
                        this.source = audioContext.createBufferSource();
                        this.source.buffer = buffer;
                        this.source.connect(audioContext.destination);

                        // 播放结束回调
                        this.source.onended = () => {
                            this.playing = false;
                            
                            // 使用setTimeout避免递归调用
                            setTimeout(() => {
                                // 如果队列中还有数据，继续播放
                                if (this.queue.length > 0) {
                                    this.startPlaying();
                                } else if (audioBufferQueue.length > 0) {
                                    // 缓冲区有新数据，进行解码
                                    const frames = [...audioBufferQueue];
                                    audioBufferQueue = [];
                                    this.decodeOpusFrames(frames);
                                } else if (this.endOfStream) {
                                    // 流已结束且没有更多数据
                                    utils.log("音频播放完成", 'info');
                                    isAudioPlaying = false;
                                    this.endOfStream = false;
                                    streamingContext = null;
                                } else {
                                    // 等待更多数据
                                    setTimeout(() => {
                                        // 如果仍然没有新数据，但有更多的包到达
                                        if (this.queue.length === 0 && audioBufferQueue.length > 0) {
                                            const frames = [...audioBufferQueue];
                                            audioBufferQueue = [];
                                            this.decodeOpusFrames(frames);
                                        } else if (this.queue.length === 0 && audioBufferQueue.length === 0) {
                                            // 真的没有更多数据了
                                            utils.log("音频播放完成 (超时)", 'info');
                                            isAudioPlaying = false;
                                            streamingContext = null;
                                        }
                                    }, 500); // 500ms超时
                                }
                            }, 10); // 10ms延迟，避免立即递归
                        };

                        this.source.start();
                    }
                };
            }

            // 开始处理缓冲的数据
            const frames = [...audioBufferQueue];
            audioBufferQueue = []; // 清空缓冲队列

            // 解码并播放
            await streamingContext.decodeOpusFrames(frames);

        } catch (error) {
            utils.log(`播放已缓冲的音频出错: ${error.message}`, 'error');
            isAudioPlaying = false;
            streamingContext = null;
        }
    };

    // 执行初始化和播放
    initDecoderAndPlay();
}

// 将Int16音频数据转换为Float32音频数据
function convertInt16ToFloat32(int16Data) {
    const float32Data = new Float32Array(int16Data.length);
    for (let i = 0; i < int16Data.length; i++) {
        // 将[-32768,32767]范围转换为[-1,1]
        float32Data[i] = int16Data[i] / (int16Data[i] < 0 ? 0x8000 : 0x7FFF);
    }
    return float32Data;
}

// 初始化Opus解码器 - 完整版本
async function initOpusDecoder() {
    if (opusDecoder) return opusDecoder; // 已经初始化

    try {
        // 检查ModuleInstance是否存在
        if (typeof window.ModuleInstance === 'undefined') {
            if (typeof Module !== 'undefined') {
                // 使用全局Module作为ModuleInstance
                window.ModuleInstance = Module;
                utils.log('使用全局Module作为ModuleInstance', 'info');
            } else {
                throw new Error('Opus库未加载，ModuleInstance和Module对象都不存在');
            }
        }

        const mod = window.ModuleInstance;

        // 创建解码器对象
        opusDecoder = {
            channels: utils.CHANNELS,
            rate: utils.SAMPLE_RATE,
            frameSize: utils.FRAME_SIZE,
            module: mod,
            decoderPtr: null, // 初始为null

            // 初始化解码器
            init: function () {
                if (this.decoderPtr) return true; // 已经初始化

                // 获取解码器大小
                const decoderSize = mod._opus_decoder_get_size(this.channels);
                utils.log(`Opus解码器大小: ${decoderSize}字节`, 'debug');

                // 分配内存
                this.decoderPtr = mod._malloc(decoderSize);
                if (!this.decoderPtr) {
                    throw new Error("无法分配解码器内存");
                }

                // 初始化解码器
                const err = mod._opus_decoder_init(
                    this.decoderPtr,
                    this.rate,
                    this.channels
                );

                if (err < 0) {
                    this.destroy(); // 清理资源
                    throw new Error(`Opus解码器初始化失败: ${err}`);
                }

                utils.log("Opus解码器初始化成功", 'success');
                return true;
            },

            // 解码方法
            decode: function (opusData) {
                if (!this.decoderPtr) {
                    if (!this.init()) {
                        throw new Error("解码器未初始化且无法初始化");
                    }
                }

                try {
                    const mod = this.module;

                    // 为Opus数据分配内存
                    const opusPtr = mod._malloc(opusData.length);
                    mod.HEAPU8.set(opusData, opusPtr);

                    // 为PCM输出分配内存
                    const pcmPtr = mod._malloc(this.frameSize * 2); // Int16 = 2字节

                    // 解码
                    const decodedSamples = mod._opus_decode(
                        this.decoderPtr,
                        opusPtr,
                        opusData.length,
                        pcmPtr,
                        this.frameSize,
                        0 // 不使用FEC
                    );

                    if (decodedSamples < 0) {
                        mod._free(opusPtr);
                        mod._free(pcmPtr);
                        throw new Error(`Opus解码失败: ${decodedSamples}`);
                    }

                    // 复制解码后的数据
                    const decodedData = new Int16Array(decodedSamples);
                    for (let i = 0; i < decodedSamples; i++) {
                        decodedData[i] = mod.HEAP16[(pcmPtr >> 1) + i];
                    }

                    // 释放内存
                    mod._free(opusPtr);
                    mod._free(pcmPtr);

                    return decodedData;
                } catch (error) {
                    utils.log(`Opus解码错误: ${error.message}`, 'error');
                    return new Int16Array(0);
                }
            },

            // 销毁方法
            destroy: function () {
                if (this.decoderPtr) {
                    this.module._free(this.decoderPtr);
                    this.decoderPtr = null;
                }
            }
        };

        // 初始化解码器
        if (!opusDecoder.init()) {
            throw new Error("Opus解码器初始化失败");
        }

        return opusDecoder;

    } catch (error) {
        utils.log(`Opus解码器初始化失败: ${error.message}`, 'error');
        opusDecoder = null; // 重置为null，以便下次重试
        throw error;
    }
}

// 清理音频缓冲
function clearAudioBuffers() {
    audioBufferQueue = [];
    isAudioBuffering = false;
    isAudioPlaying = false;
    audioChunks = [];
    if (streamingContext) {
        streamingContext = null;
    }
    utils.log('音频缓冲已清理', 'debug');
}

// 导出到全局
window.audio = {
    initAudio,
    startRecording,
    stopRecording,
    handleIncomingAudio,
    clearAudioBuffers,
    analyser,
    isRecording: () => isRecording,
    isPlaying: () => isAudioPlaying
};