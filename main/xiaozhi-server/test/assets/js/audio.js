// 音频处理模块 - 高性能流式播放版本

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
let streamingAudioNode = null;

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

        // 创建MediaRecorder，尝试不同编码选项（与原始版本保持一致）
        try {
            // 优先尝试使用Opus编码
            mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 16000
            });
            utils.log('已初始化MediaRecorder (使用Opus编码)', 'success');
            utils.log(`选择的编码格式: ${mediaRecorder.mimeType}`, 'info');
        } catch (e1) {
            try {
                // 如果Opus不支持，尝试WebM标准编码
                mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm',
                    audioBitsPerSecond: 16000
                });
                utils.log('已初始化MediaRecorder (使用WebM标准编码)', 'warning');
                utils.log(`选择的编码格式: ${mediaRecorder.mimeType}`, 'info');
            } catch (e2) {
                try {
                    // 尝试OGG+Opus
                    mediaRecorder = new MediaRecorder(stream, {
                        mimeType: 'audio/ogg;codecs=opus',
                        audioBitsPerSecond: 16000
                    });
                    utils.log('已初始化MediaRecorder (使用OGG+Opus编码)', 'warning');
                    utils.log(`选择的编码格式: ${mediaRecorder.mimeType}`, 'info');
                } catch (e3) {
                    // 最后使用默认编码
                    mediaRecorder = new MediaRecorder(stream);
                    utils.log(`已初始化MediaRecorder (使用默认编码: ${mediaRecorder.mimeType})`, 'warning');
                }
            }
        }

        // 使用简化的PCM录音方案，模仿原始test_page.html的成功方案
        setupPCMRecording(stream);
        
        // MediaRecorder作为备用（已弃用）
        setupMediaRecorderEvents();

        utils.log('音频初始化成功', 'success');
        return true;

    } catch (error) {
        utils.log(`音频初始化失败: ${error.message}`, 'error');
        return false;
    }
}


// 设置简化的PCM录音系统
let pcmRecordingContext = null;
let opusEncoder = null;
let pcmDataBuffer = new Int16Array(0);

function setupPCMRecording(stream) {
    try {
        // 创建PCM录音上下文
        pcmRecordingContext = {
            stream: stream,
            isRecording: false,
            bufferSize: 4096,
            processor: null,
            source: null
        };
        
        // 初始化Opus编码器
        initOpusEncoder();
        
        utils.log('PCM录音系统初始化成功', 'success');
    } catch (error) {
        utils.log(`PCM录音系统初始化失败: ${error.message}`, 'error');
    }
}

// 初始化Opus编码器
function initOpusEncoder() {
    try {
        if (opusEncoder) {
            return true; // 已经初始化过
        }

        if (!window.ModuleInstance && !window.Module) {
            utils.log('无法创建Opus编码器：libopus未加载', 'error');
            return false;
        }

        const mod = window.ModuleInstance || window.Module;
        const sampleRate = 16000; // 16kHz采样率
        const channels = 1;       // 单声道
        const application = 2048; // OPUS_APPLICATION_VOIP = 2048

        // 获取编码器大小
        const encoderSize = mod._opus_encoder_get_size(channels);
        utils.log(`Opus编码器大小: ${encoderSize}字节`, 'debug');

        // 分配编码器内存
        const encoderPtr = mod._malloc(encoderSize);
        if (!encoderPtr) {
            throw new Error("无法分配编码器内存");
        }

        // 初始化编码器
        const err = mod._opus_encoder_init(encoderPtr, sampleRate, channels, application);
        if (err < 0) {
            mod._free(encoderPtr);
            throw new Error(`Opus编码器初始化失败: ${err}`);
        }

        // 设置编码器参数
        mod._opus_encoder_ctl(encoderPtr, 4002, 32000); // OPUS_SET_BITRATE
        
        // 创建编码器对象
        opusEncoder = {
            channels: channels,
            rate: sampleRate,
            frameSize: 960, // 60ms @ 16kHz
            module: mod,
            encoderPtr: encoderPtr,

            encode: function(pcmData) {
                try {
                    const mod = this.module;

                    // 为PCM数据分配内存
                    const pcmPtr = mod._malloc(pcmData.length * 2); // Int16 = 2字节
                    mod.HEAP16.set(pcmData, pcmPtr >> 1);

                    // 为Opus输出分配内存（最大4000字节足够）
                    const opusPtr = mod._malloc(4000);

                    // 编码
                    const encodedLength = mod._opus_encode(
                        this.encoderPtr,
                        pcmPtr,
                        this.frameSize,
                        opusPtr,
                        4000
                    );

                    if (encodedLength < 0) {
                        mod._free(pcmPtr);
                        mod._free(opusPtr);
                        throw new Error(`Opus编码失败: ${encodedLength}`);
                    }

                    // 复制编码后的数据
                    const encodedData = new Uint8Array(encodedLength);
                    for (let i = 0; i < encodedLength; i++) {
                        encodedData[i] = mod.HEAPU8[opusPtr + i];
                    }

                    // 释放内存
                    mod._free(pcmPtr);
                    mod._free(opusPtr);

                    return encodedData;
                } catch (error) {
                    utils.log(`Opus编码错误: ${error.message}`, 'error');
                    return new Uint8Array(0);
                }
            },

            destroy: function() {
                if (this.encoderPtr) {
                    this.module._free(this.encoderPtr);
                    this.encoderPtr = null;
                }
            }
        };

        utils.log("Opus编码器初始化成功", 'success');
        return true;

    } catch (error) {
        utils.log(`Opus编码器初始化失败: ${error.message}`, 'error');
        opusEncoder = null;
        return false;
    }
}

// 开始PCM录音
function startPCMRecording() {
    if (!pcmRecordingContext || pcmRecordingContext.isRecording) return false;
    
    try {
        const context = pcmRecordingContext;
        context.isRecording = true;
        
        // 创建ScriptProcessorNode
        context.processor = audioContext.createScriptProcessor(context.bufferSize, 1, 1);
        context.source = audioContext.createMediaStreamSource(context.stream);
        
        // 处理音频数据，模仿原始test_page.html的逻辑
        let callbackCount = 0;
        context.processor.onaudioprocess = (event) => {
            callbackCount++;
            
            // 每50次回调输出一次调试信息
            if (callbackCount % 50 === 1) {
                console.log(`ScriptProcessorNode回调 #${callbackCount}，录音状态：${context.isRecording}，连接状态：${window.websocketManager?.isConnected()}`);
            }
            
            if (!context.isRecording || !window.websocketManager.isConnected()) return;
            
            const inputBuffer = event.inputBuffer;
            const inputData = inputBuffer.getChannelData(0);
            
            // 检查音频数据
            let hasAudio = false;
            for (let i = 0; i < inputData.length; i++) {
                if (Math.abs(inputData[i]) > 0.001) {
                    hasAudio = true;
                    break;
                }
            }
            
            // 将Float32转换为Int16 PCM
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                pcmData[i] = Math.max(-32768, Math.min(32767, Math.round(inputData[i] * 32767)));
            }
            
            if (callbackCount % 50 === 1) {
                console.log(`音频数据：长度=${inputData.length}，有音频=${hasAudio}，PCM样本=${pcmData.length}`);
            }
            
            // 处理PCM缓冲数据（与原始版本相同的逻辑）
            processPCMBuffer(pcmData);
        };
        
        // 连接音频链路，使用静音输出避免回音
        const gainNode = audioContext.createGain();
        gainNode.gain.value = 0;
        
        context.source.connect(context.processor);
        context.processor.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        utils.log('PCM录音已启动', 'success');
        return true;
        
    } catch (error) {
        utils.log(`PCM录音启动失败: ${error.message}`, 'error');
        if (pcmRecordingContext) pcmRecordingContext.isRecording = false;
        return false;
    }
}

// 处理PCM缓冲数据（与原始test_page.html完全相同）
function processPCMBuffer(buffer) {
    if (!pcmRecordingContext || !pcmRecordingContext.isRecording) return;

    // 将新的PCM数据追加到缓冲区
    const newBuffer = new Int16Array(pcmDataBuffer.length + buffer.length);
    newBuffer.set(pcmDataBuffer);
    newBuffer.set(buffer, pcmDataBuffer.length);
    pcmDataBuffer = newBuffer;

    // 检查是否有足够的数据进行Opus编码（16000Hz, 60ms = 960个采样点）
    const samplesPerFrame = 960; // 60ms @ 16kHz

    while (pcmDataBuffer.length >= samplesPerFrame) {
        // 从缓冲区取出一帧数据
        const frameData = pcmDataBuffer.slice(0, samplesPerFrame);
        pcmDataBuffer = pcmDataBuffer.slice(samplesPerFrame);

        // 编码为Opus并发送
        encodeAndSendOpus(frameData);
    }
}

// 编码并发送Opus数据（与原始test_page.html完全相同）
function encodeAndSendOpus(pcmData = null) {
    if (!opusEncoder) {
        utils.log('Opus编码器未初始化', 'error');
        return;
    }

    try {
        // 如果提供了PCM数据，则编码该数据
        if (pcmData) {
            // 使用已初始化的Opus编码器编码
            const opusData = opusEncoder.encode(pcmData);

            if (opusData && opusData.length > 0) {
                // 发送编码后的Opus数据
                window.websocketManager.sendBinaryData(opusData.buffer);
                console.log(`✅ 发送Opus数据，大小：${opusData.length}字节`);
                utils.log(`发送Opus数据，大小：${opusData.length}字节`, 'info');
            } else {
                console.log('❌ Opus编码失败或数据为空');
                utils.log('Opus编码失败或数据为空', 'warning');
            }
        } else {
            // 处理剩余的PCM数据
            if (pcmDataBuffer.length > 0) {
                // 如果剩余的采样点不足一帧，用静音填充
                const samplesPerFrame = 960;
                if (pcmDataBuffer.length < samplesPerFrame) {
                    const paddedBuffer = new Int16Array(samplesPerFrame);
                    paddedBuffer.set(pcmDataBuffer);
                    // 剩余部分为0（静音）
                    encodeAndSendOpus(paddedBuffer);
                } else {
                    encodeAndSendOpus(pcmDataBuffer.slice(0, samplesPerFrame));
                }
                pcmDataBuffer = new Int16Array(0);
            }
        }
    } catch (error) {
        utils.log(`Opus编码错误: ${error.message}`, 'error');
    }
}

// 停止PCM录音
function stopPCMRecording() {
    if (!pcmRecordingContext || !pcmRecordingContext.isRecording) return;
    
    try {
        const context = pcmRecordingContext;
        context.isRecording = false;
        
        // 编码并发送剩余的数据（与原始版本相同）
        encodeAndSendOpus();
        
        // 断开音频链路
        if (context.processor) {
            context.processor.disconnect();
            context.processor = null;
        }
        if (context.source) {
            context.source.disconnect();
            context.source = null;
        }
        
        utils.log('PCM录音已停止', 'success');
        
    } catch (error) {
        utils.log(`PCM录音停止失败: ${error.message}`, 'error');
    }
}

// 设置MediaRecorder事件（备用方案）
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
    if (isRecording) return;

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
            window.websocketManager.sendTextData(JSON.stringify(listenMessage));
        }

        // 确保音频上下文已启动
        if (audioContext.state === 'suspended') {
            await audioContext.resume();
            utils.log('音频上下文已恢复', 'info');
        }

        // 使用PCM录音方案
        const pcmStarted = startPCMRecording();
        if (pcmStarted) {
            isRecording = true;
            window.ui.updateRecordButtonState(true);
            
            // 开始可视化
            if (analyser) {
                const dataArray = new Uint8Array(analyser.frequencyBinCount);
                drawVisualization(dataArray);
            }
            
            utils.log('开始录音（PCM模式）', 'info');
        } else {
            utils.log('PCM录音启动失败，尝试使用MediaRecorder备用方案', 'warning');
            // 如果PCM方案失败，回退到MediaRecorder
            mediaRecorder.start(1000);
        }

    } catch (error) {
        utils.log(`录音错误: ${error.message}`, 'error');
    }
}

// 停止录音
async function stopRecording() {
    if (!isRecording) return;

    try {
        // 停止PCM录音
        stopPCMRecording();
        
        // 停止MediaRecorder（如果在使用）
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }
        
        // 更新状态
        isRecording = false;
        window.ui.updateRecordButtonState(false);
        
        // 停止可视化
        if (visualizationRequest) {
            cancelAnimationFrame(visualizationRequest);
            visualizationRequest = null;
        }
        
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
            window.websocketManager.sendTextData(JSON.stringify(stopMessage));
        }

        utils.log('停止录音（PCM模式）', 'info');

    } catch (error) {
        utils.log(`停止录音错误: ${error.message}`, 'error');
    }
}

// 处理传入的音频数据 - 高性能版本
async function handleIncomingAudio(arrayBuffer) {
    try {
        utils.log(`收到音频数据: ${arrayBuffer.byteLength} 字节`, 'debug');
        
        // 创建Uint8Array用于处理
        const opusData = new Uint8Array(arrayBuffer);

        if (opusData.length > 0) {
            // 将数据添加到缓冲队列
            audioBufferQueue.push(opusData);

            // 如果还没有开始播放，立即开始
            if (!isAudioPlaying) {
                startStreamingAudio();
            }
        } else {
            utils.log('收到空音频数据帧，结束播放', 'info');
            // 标记流结束
            if (streamingAudioNode) {
                streamingAudioNode.endOfStream = true;
            }
        }
        
    } catch (error) {
        utils.log(`处理音频数据失败: ${error.message}`, 'error');
    }
}

// 开始流式音频播放 - 使用WebAudio API的实时处理
function startStreamingAudio() {
    if (isAudioPlaying) return;
    
    isAudioPlaying = true;
    utils.log("开始流式音频播放", 'info');
    
    // 确保音频上下文存在
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: utils.SAMPLE_RATE
        });
    }
    
    // 初始化Opus解码器
    initOpusDecoder().then(decoder => {
        if (!decoder) {
            utils.log('Opus解码器初始化失败，无法播放音频', 'error');
            isAudioPlaying = false;
            return;
        }
        
        opusDecoder = decoder;
        
        // 创建流式音频节点
        streamingAudioNode = createStreamingAudioNode();
        
        // 开始处理音频数据
        processAudioQueue();
        
    }).catch(error => {
        utils.log(`初始化音频播放失败: ${error.message}`, 'error');
        isAudioPlaying = false;
    });
}

// 创建流式音频节点
function createStreamingAudioNode() {
    const bufferSize = 4096; // 使用较大的缓冲区减少回调频率
    const processor = audioContext.createScriptProcessor(bufferSize, 0, 1);
    
    // 创建环形缓冲区
    const ringBufferSize = utils.SAMPLE_RATE * 2; // 2秒缓冲区
    const ringBuffer = new Float32Array(ringBufferSize);
    let writePos = 0;
    let readPos = 0;
    
    const audioNode = {
        processor: processor,
        ringBuffer: ringBuffer,
        writePos: writePos,
        readPos: readPos,
        ringBufferSize: ringBufferSize,
        endOfStream: false,
        
        // 写入PCM数据到环形缓冲区
        writePCM: function(pcmData) {
            for (let i = 0; i < pcmData.length; i++) {
                this.ringBuffer[this.writePos] = pcmData[i];
                this.writePos = (this.writePos + 1) % this.ringBufferSize;
            }
        },
        
        // 获取可用样本数
        getAvailableSamples: function() {
            return (this.writePos - this.readPos + this.ringBufferSize) % this.ringBufferSize;
        }
    };
    
    // 设置音频处理回调
    processor.onaudioprocess = (event) => {
        const outputBuffer = event.outputBuffer;
        const outputData = outputBuffer.getChannelData(0);
        const samplesNeeded = outputBuffer.length;
        
        let samplesFilled = 0;
        
        // 从环形缓冲区填充输出
        while (samplesFilled < samplesNeeded && audioNode.getAvailableSamples() > 0) {
            outputData[samplesFilled] = audioNode.ringBuffer[audioNode.readPos];
            audioNode.readPos = (audioNode.readPos + 1) % audioNode.ringBufferSize;
            samplesFilled++;
        }
        
        // 填充剩余部分为静音
        for (let i = samplesFilled; i < samplesNeeded; i++) {
            outputData[i] = 0;
        }
        
        // 检查是否结束播放
        if (audioNode.endOfStream && audioNode.getAvailableSamples() === 0 && audioBufferQueue.length === 0) {
            stopStreamingAudio();
        }
    };
    
    // 连接到音频输出
    processor.connect(audioContext.destination);
    
    return audioNode;
}

// 处理音频队列 - 异步解码和写入
function processAudioQueue() {
    if (!streamingAudioNode || !opusDecoder) return;
    
    const processNextBatch = () => {
        if (!isAudioPlaying) return;
        
        // 批量处理音频包以减少开销
        const batchSize = Math.min(audioBufferQueue.length, 5); // 每次处理最多5个包
        
        if (batchSize > 0) {
            const frames = audioBufferQueue.splice(0, batchSize);
            
            // 异步解码
            setTimeout(() => {
                for (const frame of frames) {
                    try {
                        const decodedData = opusDecoder.decode(frame);
                        if (decodedData && decodedData.length > 0) {
                            // 转换为Float32并写入环形缓冲区
                            const floatData = convertInt16ToFloat32(decodedData);
                            streamingAudioNode.writePCM(floatData);
                        }
                    } catch (error) {
                        utils.log(`解码音频帧失败: ${error.message}`, 'warning');
                    }
                }
                
                // 继续处理下一批
                setTimeout(processNextBatch, 10); // 10ms后处理下一批
            }, 0);
        } else {
            // 没有新数据，稍后再检查
            setTimeout(processNextBatch, 20); // 20ms后再检查
        }
    };
    
    // 开始处理
    processNextBatch();
}

// 停止流式音频播放
function stopStreamingAudio() {
    if (!isAudioPlaying) return;
    
    isAudioPlaying = false;
    
    if (streamingAudioNode && streamingAudioNode.processor) {
        streamingAudioNode.processor.disconnect();
        streamingAudioNode = null;
    }
    
    utils.log("流式音频播放结束", 'info');
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
    audioChunks = [];
    
    // 停止当前播放
    if (isAudioPlaying) {
        stopStreamingAudio();
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