// One continuous PCM stream, consumed on the audio rendering thread at 24 kHz.
class PcmStreamProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.queue = [];
        this.offset = 0;
        this.samples = 0;
        this.started = false;
        this.ended = false;
        this.lastSample = 0;
        this.fadeLeft = 0;
        this.reportFrames = 0;
        this.underruns = 0;
        this.port.onmessage = ({ data }) => {
            if (data.type === 'clear') {
                this.queue = [];
                this.offset = 0;
                this.samples = 0;
                this.started = false;
                this.ended = false;
                this.fadeLeft = 120;
            } else if (data.type === 'end') {
                this.ended = true;
            } else if (data.type === 'audio') {
                this.queue.push(data.samples);
                this.samples += data.samples.length;
                this.ended = false;
            }
        };
    }

    process(inputs, outputs) {
        const out = outputs[0][0];
        if (!out) return true;
        if (!this.started && (this.samples >= 960 || (this.ended && this.samples))) {
            this.started = true;
        }
        for (let i = 0; i < out.length; i++) {
            if (this.fadeLeft) {
                out[i] = this.lastSample * (--this.fadeLeft / 120);
                continue;
            }
            if (this.started && this.samples) {
                const chunk = this.queue[0];
                out[i] = chunk[this.offset++];
                this.samples--;
                if (this.offset === chunk.length) {
                    this.queue.shift();
                    this.offset = 0;
                }
                this.lastSample = out[i];
            } else {
                if (this.started) {
                    if (!this.ended) this.underruns++;
                    this.started = false;
                    this.fadeLeft = 120;
                }
                out[i] = this.fadeLeft ? this.lastSample * (--this.fadeLeft / 120) : 0;
            }
        }
        this.reportFrames += out.length;
        if (this.reportFrames >= 2400) {
            this.reportFrames = 0;
            this.port.postMessage({ queued: this.samples, underruns: this.underruns });
        }
        return true;
    }
}
registerProcessor('pcm-stream', PcmStreamProcessor);
