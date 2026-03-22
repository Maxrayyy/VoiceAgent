let ws = null;
let mediaStream = null;
let audioContext = null;
let analyserNode = null;
let analyserDataArray = null;
let analyserSilencer = null;
let scriptProcessor = null;
let isRecording = false;
let pendingStartCommand = false;

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

window.addEventListener('DOMContentLoaded', () => {
    toastStack = document.getElementById('toastStack');
    initPanelToggle();
    initWaveStrip();
    connectWS();
    setTimeout(() => startRecording().catch(() => {}), 300);
});

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
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true } });
        audioContext = new AudioContext({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(mediaStream);
        analyserNode = audioContext.createAnalyser();
        analyserNode.fftSize = 256;
        analyserDataArray = new Uint8Array(analyserNode.fftSize);
        analyserSilencer = audioContext.createGain();
        analyserSilencer.gain.value = 0;
        source.connect(analyserNode);
        analyserNode.connect(analyserSilencer);
        analyserSilencer.connect(audioContext.destination);
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
        isRecording = true;
        status.textContent = '监听中…';
        monitorMicLevel();
        requestStartRecording();
    } catch (err) {
        console.error('microphone error', err);
        status.textContent = '无法监听';
        hint.style.display = 'block';
        throw err;
    }
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
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach((t) => t.stop());
        mediaStream = null;
    }
    analyserNode = null;
    analyserDataArray = null;
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
            document.getElementById('recordStatus').textContent = '监听中…';
            break;
        case 'recording_stopped':
            document.getElementById('recordStatus').textContent = '已暂停';
            break;
        case 'stt_partial':
            showUserLive(msg.text);
            break;
        case 'stt_final':
            finalizeUserLive(msg.text);
            break;
        case 'llm_chunk':
            ensureAssistantStream();
            appendAssistantChunk(msg.text);
            break;
        case 'llm_done':
            finalizeAssistantStream();
            break;
        case 'tts_audio':
            playTtsAudio(msg.data);
            break;
        case 'rag_sources':
            currentSources = msg.sources;
            renderSources();
            break;
        case 'error':
            pushLine(`错误：${msg.message}`, 'system');
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
let ttsQueue = [];
let ttsPlaying = false;

function playTtsAudio(base64Data) {
    const audioBytes = base64ToArrayBuffer(base64Data);
    ttsQueue.push(audioBytes);
    if (!ttsPlaying) {
        processTtsQueue();
    }
}

function processTtsQueue() {
    if (ttsQueue.length === 0) {
        ttsPlaying = false;
        return;
    }
    ttsPlaying = true;
    if (!ttsCtx) {
        ttsCtx = new AudioContext({ sampleRate: 22050 });
    }
    const audioBytes = ttsQueue.shift();
    const int16 = new Int16Array(audioBytes);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
    }
    const buffer = ttsCtx.createBuffer(1, float32.length, 22050);
    buffer.getChannelData(0).set(float32);
    const analyser = ttsCtx.createAnalyser();
    analyser.fftSize = 256;
    const dataArray = new Uint8Array(analyser.fftSize);
    const gain = ttsCtx.createGain();
    const source = ttsCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(analyser);
    analyser.connect(gain);
    gain.connect(ttsCtx.destination);
    let playing = true;
    const monitor = () => {
        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += Math.abs(dataArray[i] - 128);
        }
        const avg = sum / dataArray.length;
        ttsVolumeLevel = Math.max(0.02, Math.min(0.7, avg / 70));
        if (playing) {
            requestAnimationFrame(monitor);
        } else {
            ttsVolumeLevel = 0.02;
        }
    };
    source.onended = () => {
        playing = false;
        ttsVolumeLevel = 0.02;
        processTtsQueue();
    };
    source.start();
    monitor();
}

function interrupt() {
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
