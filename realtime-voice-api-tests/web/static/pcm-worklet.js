class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const config = options.processorOptions || {};
    this.targetRate = config.targetRate || 16000;
    this.chunkFrames = Math.max(160, Math.round(this.targetRate * 0.02));
    this.ratio = sampleRate / this.targetRate;
    this.source = [];
    this.output = [];
    this.position = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || input.length === 0) {
      return true;
    }

    for (let index = 0; index < input.length; index += 1) {
      this.source.push(input[index]);
    }

    while (this.position + 1 < this.source.length) {
      const leftIndex = Math.floor(this.position);
      const fraction = this.position - leftIndex;
      const sample =
        this.source[leftIndex] * (1 - fraction) +
        this.source[leftIndex + 1] * fraction;
      this.output.push(sample);
      this.position += this.ratio;

      if (this.output.length >= this.chunkFrames) {
        const pcm = new Int16Array(this.chunkFrames);
        for (let index = 0; index < this.chunkFrames; index += 1) {
          const value = Math.max(-1, Math.min(1, this.output[index]));
          pcm[index] = value < 0 ? value * 32768 : value * 32767;
        }
        this.output.splice(0, this.chunkFrames);
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
      }
    }

    const consumed = Math.floor(this.position);
    if (consumed > 0) {
      this.source.splice(0, consumed);
      this.position -= consumed;
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);

