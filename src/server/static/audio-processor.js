/**
 * AudioWorklet 处理器 - 在独立音频线程中运行
 * 将麦克风 Float32 PCM 转换为 Int16 PCM 并发送到主线程
 */
class RecorderProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 4096;
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];

        // 没有输入或输入为空
        if (!input || input.length === 0) {
            return true;
        }

        const inputChannel = input[0];

        // 累积音频数据到缓冲区
        for (let i = 0; i < inputChannel.length; i++) {
            this.buffer[this.bufferIndex++] = inputChannel[i];

            // 缓冲区满时，转换并发送
            if (this.bufferIndex >= this.bufferSize) {
                this.sendBuffer();
                this.bufferIndex = 0;
            }
        }

        return true;
    }

    sendBuffer() {
        // Float32 转 Int16 PCM
        const pcm16 = new Int16Array(this.bufferSize);
        for (let i = 0; i < this.bufferSize; i++) {
            const s = Math.max(-1, Math.min(1, this.buffer[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // 发送到主线程（转移所有权以提高性能）
        this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
}

registerProcessor('recorder-processor', RecorderProcessor);
