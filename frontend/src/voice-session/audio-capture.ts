export function float32ToPcm16(samples: Float32Array): Uint8Array {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);

  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    const scaled = clamped < 0
      ? Math.round(clamped * 32768)
      : Math.round(clamped * 32767);
    view.setInt16(index * 2, scaled, true);
  });

  return bytes;
}

export function downsampleTo16k(
  samples: Float32Array,
  inputRate: number,
): number[] {
  if (!Number.isFinite(inputRate) || inputRate < 16_000) {
    throw new Error("VOICE_CAPTURE_SAMPLE_RATE_TOO_LOW");
  }
  if (inputRate === 16_000) {
    return Array.from(samples, (sample) => Number(sample.toFixed(6)));
  }

  const ratio = inputRate / 16_000;
  const outputLength = Math.floor(samples.length / ratio);
  const output: number[] = [];

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const start = Math.floor(outputIndex * ratio);
    const end = Math.max(start + 1, Math.floor((outputIndex + 1) * ratio));
    let sum = 0;
    let count = 0;

    for (let inputIndex = start; inputIndex < end && inputIndex < samples.length; inputIndex += 1) {
      sum += samples[inputIndex];
      count += 1;
    }

    output.push(Number((count ? sum / count : 0).toFixed(6)));
  }

  return output;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const block = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += block) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + block));
  }
  return btoa(binary);
}

export type MicrophoneFrame = {
  float32: Float32Array;
  pcm16k: Uint8Array;
};

export type MicrophoneFrameHandler = (frame: MicrophoneFrame) => void;

export class MicrophonePcmCapture {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private silentGain: GainNode | null = null;

  async start(onFrame: MicrophoneFrameHandler): Promise<void> {
    if (this.stream) return;

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const context = new AudioContext({ latencyHint: "interactive" });
    const source = context.createMediaStreamSource(stream);
    const silentGain = context.createGain();
    silentGain.gain.value = 0;
    silentGain.connect(context.destination);

    const deliver = (samples: Float32Array) => {
      if (!samples.length) return;
      const pcm16k = float32ToPcm16(
        new Float32Array(downsampleTo16k(samples, context.sampleRate)),
      );
      onFrame({ float32: samples, pcm16k });
    };

    try {
      if (context.audioWorklet) {
        await context.audioWorklet.addModule(
          `${import.meta.env.BASE_URL}voice/pcm-capture.worklet.js`,
        );
        const worklet = new AudioWorkletNode(context, "deus-pcm-capture", {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [1],
        });
        worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
          deliver(event.data);
        };
        source.connect(worklet);
        worklet.connect(silentGain);
        this.worklet = worklet;
      } else {
        const processor = context.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (event) => {
          deliver(new Float32Array(event.inputBuffer.getChannelData(0)));
        };
        source.connect(processor);
        processor.connect(silentGain);
        this.processor = processor;
      }

      this.stream = stream;
      this.context = context;
      this.source = source;
      this.silentGain = silentGain;
      if (context.state === "suspended") {
        await context.resume().catch(() => undefined);
      }
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      await context.close().catch(() => undefined);
      throw error;
    }
  }

  async resume(): Promise<void> {
    if (this.context?.state === "suspended") await this.context.resume();
  }

  async stop(): Promise<void> {
    this.worklet?.disconnect();
    this.processor?.disconnect();
    this.source?.disconnect();
    this.silentGain?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    const context = this.context;
    this.stream = null;
    this.context = null;
    this.source = null;
    this.worklet = null;
    this.processor = null;
    this.silentGain = null;
    if (context && context.state !== "closed") {
      await context.close().catch(() => undefined);
    }
  }
}
