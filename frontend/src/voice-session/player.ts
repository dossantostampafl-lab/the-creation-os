export type AudioSink = {
  push: (chunk: Uint8Array) => void;
  stop: () => void;
};

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
