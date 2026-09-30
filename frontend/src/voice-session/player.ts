export type AudioSink = {
  push: (chunk: Uint8Array) => void;
  stop: () => void;
};

export const voiceActivity = { level: 0 };

export class Pcm16AudioSink implements AudioSink {
  private readonly context: AudioContext;
  private readonly sampleRate: number;
  private nextStart = 0;
  private readonly sources = new Set<AudioBufferSourceNode>();

  constructor(sampleRate = 24_000) {
    this.context = new AudioContext({ latencyHint: "interactive", sampleRate });
    this.sampleRate = sampleRate;
    if (this.context.state === "suspended") {
      void this.context.resume().catch(() => undefined);
    }
  }

  async resume(): Promise<void> {
    if (this.context.state === "suspended") await this.context.resume();
  }

  push(chunk: Uint8Array): void {
    if (chunk.byteLength < 2) return;
    const sampleCount = Math.floor(chunk.byteLength / 2);
    const audioBuffer = this.context.createBuffer(1, sampleCount, this.sampleRate);
    const channel = audioBuffer.getChannelData(0);
    const view = new DataView(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    let energy = 0;
    for (let index = 0; index < sampleCount; index += 1) {
      const value = view.getInt16(index * 2, true);
      const normalized = value < 0 ? value / 32768 : value / 32767;
      channel[index] = normalized;
      energy += normalized * normalized;
    }
    voiceActivity.level = Math.min(1, Math.sqrt(energy / sampleCount) * 4);

    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);
    const start = Math.max(this.context.currentTime + 0.01, this.nextStart);
    this.nextStart = start + audioBuffer.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
    source.start(start);
  }

  stop(): void {
    for (const source of this.sources) {
      try { source.stop(); } catch { /* already stopped */ }
    }
    this.sources.clear();
    this.nextStart = this.context.currentTime;
    voiceActivity.level = 0;
  }

  async close(): Promise<void> {
    this.stop();
    if (this.context.state !== "closed") await this.context.close();
  }
}

export class StreamingAudioPlayer {
  private activeTurnId: number | null = null;

  constructor(private readonly sink: AudioSink) {}

  startTurn(turnId: number): void {
    if (this.activeTurnId !== null && this.activeTurnId !== turnId) {
      this.sink.stop();
    }
    this.activeTurnId = turnId;
  }

  push(turnId: number, chunk: Uint8Array): void {
    if (this.activeTurnId !== turnId || !chunk.byteLength) return;
    this.sink.push(chunk);
  }

  cancel(turnId: number): boolean {
    if (this.activeTurnId !== turnId) return false;
    this.activeTurnId = null;
    this.sink.stop();
    return true;
  }

  finish(turnId: number): boolean {
    if (this.activeTurnId !== turnId) return false;
    this.activeTurnId = null;
    return true;
  }
}
