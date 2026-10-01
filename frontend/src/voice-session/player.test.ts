import { describe, expect, it, vi } from "vitest";

import { Pcm16AudioSink, StreamingAudioPlayer } from "./player";

class FakeSink {
  readonly chunks: Uint8Array[] = [];
  stops = 0;

  push(chunk: Uint8Array): void {
    this.chunks.push(chunk);
  }

  stop(): void {
    this.stops += 1;
  }
}

describe("StreamingAudioPlayer", () => {
  it("waits for the last scheduled audio source before listening can resume", async () => {
    const sources: Array<{ onended: (() => void) | null; connect: () => void; start: () => void; stop: () => void }> = [];
    class Context {
      state = "running";
      currentTime = 0;
      destination = {};
      createBuffer(_channels: number, count: number, rate: number) {
        return { duration: count / rate, getChannelData: () => new Float32Array(count) };
      }
      createBufferSource() {
        const source = { onended: null as (() => void) | null, connect() {}, start() {}, stop() {} };
        sources.push(source);
        return source;
      }
    }
    vi.stubGlobal("AudioContext", Context);
    try {
      const sink = new Pcm16AudioSink();
      sink.push(new Uint8Array([0, 0]));
      sink.push(new Uint8Array([0, 0]));
      let drained = false;
      const completion = sink.whenDrained().then(() => { drained = true; });
      sources[0].onended?.();
      await Promise.resolve();
      expect(drained).toBe(false);
      sources[1].onended?.();
      await completion;
      expect(drained).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("plays audio only for the active turn and ignores stale chunks", () => {
    const sink = new FakeSink();
    const player = new StreamingAudioPlayer(sink);

    player.startTurn(2);
    player.push(2, new Uint8Array([2]));
    player.push(1, new Uint8Array([1]));

    expect(sink.chunks.map((chunk) => Array.from(chunk))).toEqual([[2]]);
  });

  it("stops the active turn immediately on barge-in", () => {
    const sink = new FakeSink();
    const player = new StreamingAudioPlayer(sink);

    player.startTurn(3);
    player.push(3, new Uint8Array([3]));
    expect(player.cancel(3)).toBe(true);
    player.push(3, new Uint8Array([4]));

    expect(sink.stops).toBe(1);
    expect(sink.chunks.map((chunk) => Array.from(chunk))).toEqual([[3]]);
  });

  it("does not let a stale cancellation stop a newer turn", () => {
    const sink = new FakeSink();
    const player = new StreamingAudioPlayer(sink);

    player.startTurn(4);
    expect(player.cancel(3)).toBe(false);
    player.push(4, new Uint8Array([4]));

    expect(sink.stops).toBe(0);
    expect(sink.chunks.map((chunk) => Array.from(chunk))).toEqual([[4]]);
  });

  it("stops acknowledgement audio even after its synthetic turn was finished", () => {
    const sink = new FakeSink();
    const player = new StreamingAudioPlayer(sink);

    player.startTurn(0);
    player.push(0, new Uint8Array([1]));
    expect(player.finish(0)).toBe(true);
    player.stop();

    expect(sink.stops).toBe(1);
  });
});
