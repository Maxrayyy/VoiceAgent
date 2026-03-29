let ws = null;
let mediaStream = null;
let audioContext = null;
let analyserNode = null;
let analyserDataArray = null;
let analyserSilencer = null;
let scriptProcessor = null;
let audioWorkletNode = null;
let isRecording = false;
let pendingStartCommand = false;
let useAudioWorklet = true;

let micVolumeLevel = 0.02;
let ttsVolumeLevel = 0.02;
let volumeCanvas;
let volumeCtx;
let volumeValues = [];

let dialogueLines = [];
const maxLines = 12;

let liveUserEl = null;
let streamingAssistantEl = null;
let streamingAssistantText = '';
let currentSources = [];
let toastStack = null;

// 打断拦截：收到 tts_interrupted 后忽略后续 tts_audio
let ttsIgnore = false;

// 录音模式: 'continuous' (持续监听) 或 'push-to-talk' (按住说话)
let recordMode = 'continuous';

// AI 是否正在回复（控制打断按钮显隐）
let aiResponding = false;

window.addEventListener('DOMContentLoaded', () => {
    toastStack = document.getElementById('toastStack');
    initPanelToggle();
    initWaveStrip();
    initActionBar();
    connectWS();
    // continuous 模式自动开始录音
    setTimeout(() => {
        if (recordMode === 'continuous') {
            startRecording().catch(() => {});
        }
    }, 300);
});

function initActionBar() {
    const pttBtn = document.getElementById('pttBtn');

    // PTT: 按下开始录音，松开停止
    pttBtn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (recordMode !== 'push-to-talk') return;
        pttBtn.classList.add('active');
        startRecording().catch(() => {});
    });
    pttBtn.addEventListener('mouseup', () => {
        if (recordMode !== 'push-to-talk') return;
        pttBtn.classList.remove('active');
        // 延迟 200ms 停止录音，确保最后的音频 chunk 被发送
        setTimeout(() => stopRecording(), 200);
    });
    pttBtn.addEventListener('mouseleave', () => {
        if (recordMode !== 'push-to-talk' || !pttBtn.classList.contains('active')) return;
        pttBtn.classList.remove('active');
        setTimeout(() => stopRecording(), 200);
    });

    // 触摸支持
    pttBtn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        if (recordMode !== 'push-to-talk') return;
        pttBtn.classList.add('active');
        startRecording().catch(() => {});
    });
    pttBtn.addEventListener('touchend', (e) => {
        e.preventDefault();
        if (recordMode !== 'push-to-talk') return;
        pttBtn.classList.remove('active');
        setTimeout(() => stopRecording(), 200);
    });
    pttBtn.addEventListener('touchcancel', () => {
        if (recordMode !== 'push-to-talk') return;
        pttBtn.classList.remove('active');
        setTimeout(() => stopRecording(), 200);
    });

    updateModeUI();
}

function toggleRecordMode() {
    // 切换模式时清空状态，相当于新会话
    stopRecording();
    resetTtsPlayback();
    setAiResponding(false);
    ttsIgnore = true;
    clearHistory();

    if (recordMode === 'continuous') {
        recordMode = 'push-to-talk';
    } else {
        recordMode = 'continuous';
        startRecording().catch(() => {});
    }
    updateModeUI();
}

function updateModeUI() {
    const modeBtn = document.getElementById('modeBtn');
    const pttBtn = document.getElementById('pttBtn');
    const status = document.getElementById('recordStatus');

    if (recordMode === 'continuous') {
        modeBtn.textContent = '持续监听';
        pttBtn.classList.remove('visible');
        status.textContent = isRecording ? '监听中…' : '正在初始化…';
    } else {
        modeBtn.textContent = '按住说话';
        pttBtn.classList.add('visible');
        status.textContent = '等待说话…';
    }
}

function setAiResponding(responding) {
    aiResponding = responding;
    const btn = document.getElementById('interruptBtn');
    if (responding) {
        btn.classList.add('visible');
    } else {
        btn.classList.remove('visible');
    }
}

function initPanelToggle() {
    const toggle = document.getElementById('panelToggle');
    const panel = document.getElementById('controlPanel');
    const brand = document.getElementById('brandCluster');
    const togglePanel = () => {
        panel.classList.toggle('open');
        brand.classList.toggle('panel-open');
    };
    toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        togglePanel();
    });
    document.addEventListener('click', (e) => {
        if (!panel.contains(e.target) && !toggle.contains(e.target) && panel.classList.contains('open')) {
            panel.classList.remove('open');
            brand.classList.remove('panel-open');
        }
    });
}

function initWaveStrip() {
    volumeCanvas = document.getElementById('volumeCanvas');
    if (!volumeCanvas) return;
    volumeCtx = volumeCanvas.getContext('2d');
    const resize = () => {
        const ratio = window.devicePixelRatio || 1;
        volumeCanvas.width = volumeCanvas.clientWidth * ratio;
        volumeCanvas.height = volumeCanvas.clientHeight * ratio;
        volumeCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);
    volumeValues = new Array(220).fill(0.02);
    const draw = () => {
        const blended = Math.max(micVolumeLevel, ttsVolumeLevel * 0.85);
        volumeValues.push(blended);
        volumeValues.shift();
        paintWave();
        requestAnimationFrame(draw);
    };
    draw();
}

function paintWave() {
    if (!volumeCtx || !volumeCanvas) return;
    const width = volumeCanvas.clientWidth;
    const height = volumeCanvas.clientHeight;
    const mid = height / 2;
    volumeCtx.clearRect(0, 0, width, height);
    volumeCtx.beginPath();
    volumeCtx.moveTo(0, mid);
    volumeValues.forEach((val, idx) => {
        const x = (idx / (volumeValues.length - 1)) * width;
        const y = mid + (val - 0.02) * height * 0.8 * (Math.sin(idx / 4) * 0.12 + 1);
        volumeCtx.lineTo(x, y);
    });
    const gradient = volumeCtx.createLinearGradient(0, mid - 20, 0, mid + 20);
    gradient.addColorStop(0, 'rgba(0,0,0,0.35)');
    gradient.addColorStop(0.5, 'rgba(0,0,0,0.55)');
    gradient.addColorStop(1, 'rgba(0,0,0,0.35)');
    volumeCtx.strokeStyle = gradient;
    volumeCtx.lineWidth = 2;
    volumeCtx.stroke();
}

function connectWS() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);
    ws.onopen = () => {
        console.log('WebSocket connected');
        if (pendingStartCommand || isRecording) {
            requestStartRecording();
        }
    };
    ws.onclose = () => setTimeout(connectWS, 2000);
    ws.onerror = (e) => console.error('WebSocket error', e);
    ws.onmessage = (event) => handleMessage(JSON.parse(event.data));
}

async function startRecording() {
    if (isRecording) return;
    const status = document.getElementById('recordStatus');
    const hint = document.getElementById('permissionHint');
    hint.style.display = 'none';
    status.textContent = '请求麦克风权限…';
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });
        audioContext = new AudioContext({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(mediaStream);

        // 音量分析器
        analyserNode = audioContext.createAnalyser();
        analyserNode.fftSize = 256;
        analyserDataArray = new Uint8Array(analyserNode.fftSize);
        analyserSilencer = audioContext.createGain();
        analyserSilencer.gain.value = 0;
        source.connect(analyserNode);
        analyserNode.connect(analyserSilencer);
        analyserSilencer.connect(audioContext.destination);

        // 尝试使用 AudioWorklet（现代方案）
        if (useAudioWorklet && audioContext.audioWorklet) {
            try {
                await audioContext.audioWorklet.addModule('/static/audio-processor.js');
                audioWorkletNode = new AudioWorkletNode(audioContext, 'recorder-processor');

                audioWorkletNode.port.onmessage = (e) => {
                    if (!isRecording) return;
                    const b64 = arrayBufferToBase64(e.data);
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ type: 'audio', data: b64 }));
                    }
                };

                source.connect(audioWorkletNode);
                audioWorkletNode.connect(audioContext.destination);
                console.log('Using AudioWorklet for recording');
            } catch (workletErr) {
                console.warn('AudioWorklet failed, falling back to ScriptProcessor:', workletErr);
                useAudioWorklet = false;
                setupScriptProcessor(source);
            }
        } else {
            // 降级方案：使用 ScriptProcessorNode
            setupScriptProcessor(source);
        }

        isRecording = true;
        status.textContent = recordMode === 'continuous' ? '监听中…' : '录音中…';
        monitorMicLevel();
        requestStartRecording();
    } catch (err) {
        console.error('microphone error', err);
        status.textContent = '无法监听';
        hint.style.display = 'block';
        throw err;
    }
}

function setupScriptProcessor(source) {
    scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    scriptProcessor.onaudioprocess = (e) => {
        if (!isRecording) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const pcm16 = float32ToPCM16(float32);
        const b64 = arrayBufferToBase64(pcm16.buffer);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'audio', data: b64 }));
        }
    };
    source.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);
    console.log('Using ScriptProcessor for recording (legacy)');
}

function monitorMicLevel() {
    const sample = () => {
        if (!analyserNode || !analyserDataArray) {
            micVolumeLevel = 0.02;
            return;
        }
        analyserNode.getByteTimeDomainData(analyserDataArray);
        let sum = 0;
        for (let i = 0; i < analyserDataArray.length; i++) {
            sum += Math.abs(analyserDataArray[i] - 128);
        }
        const avg = sum / analyserDataArray.length;
        micVolumeLevel = Math.min(0.9, Math.max(avg / 60, 0.02));
        if (isRecording) {
            requestAnimationFrame(sample);
        }
    };
    sample();
}

function stopRecording() {
    if (!isRecording) return;
    isRecording = false;
    pendingStartCommand = false;

    // 清理 ScriptProcessor
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }

    // 清理 AudioWorklet
    if (audioWorkletNode) {
        audioWorkletNode.port.onmessage = null;
        audioWorkletNode.disconnect();
        audioWorkletNode = null;
    }

    // 关闭 AudioContext
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    // 停止媒体流
    if (mediaStream) {
        mediaStream.getTracks().forEach((t) => t.stop());
        mediaStream = null;
    }

    analyserNode = null;
    analyserDataArray = null;

    // 通知后端
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop_recording' }));
    }
}

function requestStartRecording() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'start_recording' }));
        pendingStartCommand = false;
    } else {
        pendingStartCommand = true;
    }
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'recording_started':
            if (recordMode === 'continuous') {
                document.getElementById('recordStatus').textContent = '监听中…';
            } else {
                document.getElementById('recordStatus').textContent = '录音中…';
            }
            break;
        case 'recording_stopped':
            if (recordMode === 'continuous') {
                document.getElementById('recordStatus').textContent = '已暂停';
            } else {
                document.getElementById('recordStatus').textContent = '等待说话…';
            }
            break;
        case 'stt_partial':
            showUserLive(msg.text);
            break;
        case 'stt_final':
            finalizeUserLive(msg.text);
            break;
        case 'llm_chunk':
            ttsIgnore = false;
            if (!aiResponding) {
                // 新回复的第一个 chunk，重置预缓冲
                ttsBuffering = true;
                ttsPreBuffer = [];
                ttsPreBufferSamples = 0;
            }
            setAiResponding(true);
            ensureAssistantStream();
            appendAssistantChunk(msg.text);
            break;
        case 'llm_done':
            finalizeAssistantStream();
            // 不在此处隐藏打断按钮，等 TTS 播放完毕再隐藏
            break;
        case 'tts_audio':
            // 被打断后忽略残余音频
            if (!ttsIgnore) {
                enqueueTtsAudio(msg.data);
            }
            break;
        case 'tts_done':
            // TTS 合成完毕，刷新预缓冲中的剩余音频
            flushTtsPreBuffer();
            setAiResponding(false);
            break;
        case 'tts_interrupted':
            // 后端确认打断，拦截后续残余音频
            ttsIgnore = true;
            setAiResponding(false);
            finalizeAssistantStream();
            break;
        case 'rag_sources':
            currentSources = msg.sources;
            renderSources();
            break;
        case 'error':
            pushLine(`错误：${msg.message}`, 'system');
            setAiResponding(false);
            break;
        case 'history_cleared':
            dialogueLines = [];
            renderLines();
            if (liveUserEl) {
                liveUserEl.remove();
                liveUserEl = null;
            }
            if (streamingAssistantEl) {
                streamingAssistantEl.remove();
                streamingAssistantEl = null;
                streamingAssistantText = '';
            }
            showToast('上下文已清除');
            break;
    }
}

function showUserLive(text) {
    if (!text) return;
    if (!liveUserEl) {
        liveUserEl = createBubble('user', '');
        document.getElementById('dialogueCanvas').appendChild(liveUserEl);
    }
    const bubble = liveUserEl.querySelector('.bubble-card');
    bubble.textContent = text;
}

function finalizeUserLive(text) {
    if (liveUserEl) {
        liveUserEl.remove();
        liveUserEl = null;
    }
    if (text && text.trim()) {
        pushLine(text.trim(), 'user');
    }
}

function ensureAssistantStream() {
    if (!streamingAssistantEl) {
        streamingAssistantText = '';
        streamingAssistantEl = createBubble('assistant', '…');
        document.getElementById('dialogueCanvas').appendChild(streamingAssistantEl);
    }
}

function appendAssistantChunk(chunk) {
    if (!streamingAssistantEl) return;
    streamingAssistantText += chunk;
    streamingAssistantEl.querySelector('.bubble-card').textContent = streamingAssistantText;
}

function finalizeAssistantStream() {
    if (streamingAssistantEl) {
        const text = streamingAssistantText.trim();
        streamingAssistantEl.remove();
        streamingAssistantEl = null;
        streamingAssistantText = '';
        if (text) {
            pushLine(text, 'assistant');
        }
    }
}

function pushLine(text, role = 'user') {
    dialogueLines.push({ role, text });
    if (dialogueLines.length > maxLines) {
        dialogueLines = dialogueLines.slice(-maxLines);
    }
    renderLines();
}

function renderLines() {
    const canvas = document.getElementById('dialogueCanvas');
    canvas.innerHTML = '';
    dialogueLines.forEach((line) => {
        const row = createBubble(line.role, line.text);
        canvas.appendChild(row);
    });
}

function createBubble(role, text) {
    const row = document.createElement('div');
    row.className = `bubble-row ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble-card';
    bubble.textContent = text;
    row.appendChild(bubble);
    return row;
}

function renderSources() {
    const list = document.getElementById('sourcesList');
    if (!list) return;
    if (!currentSources || currentSources.length === 0) {
        list.innerHTML = '<div class="sources-empty">暂无来源</div>';
        return;
    }
    list.innerHTML = currentSources.map((s) => {
        const title = escapeHtml(s.source || '未知来源');
        const snippet = escapeHtml((s.content || '').slice(0, 160));
        const score = typeof s.score === 'number' ? `${(s.score * 100).toFixed(1)}%` : '';
        return `
            <div class="source-item">
                <div>${snippet}</div>
                <div class="source-meta">${title} ${score}</div>
            </div>
        `;
    }).join('');
}

let ttsCtx = null;
let ttsAnalyser = null;
let ttsGain = null;
let nextStartTime = 0;
let ttsMonitoring = false;
let ttsDataArray = null;

// TTS 预缓冲：累积足够音频后再开始播放，避免开头卡顿
let ttsPreBuffer = [];           // 预缓冲队列（base64 数据）
let ttsPreBufferSamples = 0;     // 已缓冲的采样数
let ttsBuffering = true;         // 是否处于缓冲阶段
const TTS_PREBUFFER_SECONDS = 0.8; // 预缓冲时长阈值（秒）
const TTS_SAMPLE_RATE = 22050;

function enqueueTtsAudio(base64Data) {
    if (ttsBuffering) {
        // 缓冲阶段：累积音频数据
        ttsPreBuffer.push(base64Data);
        const audioBytes = base64ToArrayBuffer(base64Data);
        ttsPreBufferSamples += audioBytes.byteLength / 2; // 16-bit = 2 bytes/sample

        // 缓冲够了，一次性播放
        if (ttsPreBufferSamples / TTS_SAMPLE_RATE >= TTS_PREBUFFER_SECONDS) {
            flushTtsPreBuffer();
        }
    } else {
        // 缓冲阶段结束，即时播放
        playTtsAudio(base64Data);
    }
}

function flushTtsPreBuffer() {
    if (!ttsBuffering) return;
    ttsBuffering = false;
    // 一次性提交所有缓冲的音频块
    for (const data of ttsPreBuffer) {
        playTtsAudio(data);
    }
    ttsPreBuffer = [];
    ttsPreBufferSamples = 0;
}

function playTtsAudio(base64Data) {
    // 初始化 AudioContext 和复用的音频节点
    if (!ttsCtx) {
        ttsCtx = new AudioContext({ sampleRate: TTS_SAMPLE_RATE });
        ttsAnalyser = ttsCtx.createAnalyser();
        ttsAnalyser.fftSize = 256;
        ttsDataArray = new Uint8Array(ttsAnalyser.fftSize);
        ttsGain = ttsCtx.createGain();
        ttsGain.gain.value = 1.0;
        ttsAnalyser.connect(ttsGain);
        ttsGain.connect(ttsCtx.destination);
    }

    // 解码音频数据
    const audioBytes = base64ToArrayBuffer(base64Data);
    const int16 = new Int16Array(audioBytes);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
    }

    // 创建 AudioBuffer
    const buffer = ttsCtx.createBuffer(1, float32.length, TTS_SAMPLE_RATE);
    buffer.getChannelData(0).set(float32);

    // 创建 BufferSource 并连接到复用的分析器
    const source = ttsCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(ttsAnalyser);

    // 计算预调度时间，实现无缝拼接
    const now = ttsCtx.currentTime;
    const scheduledTime = Math.max(now, nextStartTime);
    nextStartTime = scheduledTime + buffer.duration;

    // 启动播放（预调度）
    source.start(scheduledTime);

    // 启动音量监控（仅一次）
    if (!ttsMonitoring) {
        ttsMonitoring = true;
        monitorTtsVolume();
    }
}

function monitorTtsVolume() {
    if (!ttsAnalyser || !ttsDataArray) {
        ttsVolumeLevel = 0.02;
        ttsMonitoring = false;
        return;
    }

    ttsAnalyser.getByteTimeDomainData(ttsDataArray);
    let sum = 0;
    for (let i = 0; i < ttsDataArray.length; i++) {
        sum += Math.abs(ttsDataArray[i] - 128);
    }
    const avg = sum / ttsDataArray.length;
    ttsVolumeLevel = Math.max(0.02, Math.min(0.7, avg / 70));

    // 检查是否还有音频在播放
    const now = ttsCtx.currentTime;
    if (now < nextStartTime - 0.1) {
        requestAnimationFrame(monitorTtsVolume);
    } else {
        ttsVolumeLevel = 0.02;
        ttsMonitoring = false;
    }
}

function resetTtsPlayback() {
    // 重置播放状态（用于打断）
    nextStartTime = 0;
    ttsVolumeLevel = 0.02;
    ttsMonitoring = false;
    // 清空预缓冲
    ttsPreBuffer = [];
    ttsPreBufferSamples = 0;
    ttsBuffering = true;
    if (ttsCtx) {
        const ctx = ttsCtx;
        ttsCtx = null;
        ttsAnalyser = null;
        ttsGain = null;
        ttsDataArray = null;
        ctx.close().catch(() => {});
    }
}

function interrupt() {
    // 立即停止 TTS 播放
    resetTtsPlayback();

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'interrupt' }));
    }
    showToast('已发送打断指令');
}

function clearHistory() {
    dialogueLines = [];
    renderLines();
    if (liveUserEl) {
        liveUserEl.remove();
        liveUserEl = null;
    }
    if (streamingAssistantEl) {
        streamingAssistantEl.remove();
        streamingAssistantEl = null;
        streamingAssistantText = '';
    }
    showToast('正在清除上下文…');
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'clear_history' }));
    }
}

function float32ToPCM16(float32Array) {
    const pcm16 = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return pcm16;
}

function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(text, duration = 2400) {
    if (!toastStack) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = text;
    toastStack.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, duration);
}

window.startRecording = startRecording;
window.stopRecording = stopRecording;
window.interrupt = interrupt;
window.clearHistory = clearHistory;
window.toggleRecordMode = toggleRecordMode;
