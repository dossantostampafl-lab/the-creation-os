import { describe, expect, it } from "vitest";

import { StreamingAudioPlayer } from "./player";

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
});
