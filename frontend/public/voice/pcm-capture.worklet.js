class DeusPcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (input && input.length) this.port.postMessage(new Float32Array(input));
    return true;
  }
}

registerProcessor("deus-pcm-capture", DeusPcmCaptureProcessor);
