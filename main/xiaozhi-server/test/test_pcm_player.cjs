const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
let Processor;
const sandbox = {
  AudioWorkletProcessor: class { constructor() { this.port = { postMessage() {} }; } },
  registerProcessor(name, cls) { Processor = cls; },
};
vm.runInNewContext(fs.readFileSync(`${__dirname}/js/core/audio/pcm-worklet.js`, 'utf8'), sandbox);
const p = new Processor();
const input = Float32Array.from({length: 24000 * 12}, (_, i) => Math.sin(i * .03) * .2);
for (let i = 0; i < input.length; i += 997) p.port.onmessage({data:{type:'audio',samples:input.slice(i,i+997)}});
p.port.onmessage({data:{type:'end'}});
let at = 0;
while(at < input.length) {
  const out = new Float32Array(128);
  p.process([], [[out]]);
  for(let i=0;i<out.length && at<input.length;i++,at++) assert.equal(out[i],input[at]);
}
assert.equal(p.underruns,0);
assert.equal(p.samples,0);
// Clearing drops queued speech and fades the last output rather than replaying data.
p.port.onmessage({data:{type:'clear'}});
const out = new Float32Array(128);p.process([],[[out]]);
assert.equal(out[127],0);
assert.equal(p.samples,0);
// A final packet shorter than the prebuffer still drains.
const short = new Processor();
short.port.onmessage({data:{type:'audio',samples:new Float32Array([.2,.3,.4])}});
short.port.onmessage({data:{type:'end'}});
const tail = new Float32Array(128);short.process([],[[tail]]);
assert.equal(tail[0],Math.fround(.2));assert.equal(short.samples,0);
console.log('12-second continuous PCM, arbitrary packet boundaries, clear and short-tail drain: OK');
