import { describe, expect, it } from "vitest";

import { downsampleTo16k, ensureAudioContextRunning, float32ToPcm16 } from "./audio-capture";

describe("realtime microphone PCM", () => {
  it("converts normalized float audio to little-endian PCM16", () => {
    const pcm = float32ToPcm16(new Float32Array([-1, -0.5, 0, 0.5, 1]));
    const view = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);

    expect(Array.from({ length: 5 }, (_, index) => view.getInt16(index * 2, true))).toEqual([
      -32768,
      -16384,
      0,
      16384,
      32767,
    ]);
  });

  it("downsamples 48 kHz mono audio to 16 kHz deterministically", () => {
    const input = new Float32Array([
      0, 0, 0,
      0.3, 0.3, 0.3,
      -0.6, -0.6, -0.6,
    ]);

    expect(Array.from(downsampleTo16k(input, 48_000))).toEqual([0, 0.3, -0.6]);
  });

  it("rejects unsupported input rates below 16 kHz", () => {
    expect(() => downsampleTo16k(new Float32Array([0]), 8_000)).toThrow(
      "VOICE_CAPTURE_SAMPLE_RATE_TOO_LOW",
    );
  });
  it("does not report wake capture ready while the browser keeps AudioContext suspended", async () => {
    const context = {
      state: "suspended" as AudioContextState,
      resume: async () => undefined,
    };
    await expect(ensureAudioContextRunning(context)).rejects.toThrow(
      "VOICE_CAPTURE_REQUIRES_USER_GESTURE",
    );
  });

  it("accepts capture after a user gesture lets AudioContext enter running state", async () => {
    let state: AudioContextState = "suspended";
    const context = {
      get state() { return state; },
      resume: async () => { state = "running"; },
    };
    await expect(ensureAudioContextRunning(context)).resolves.toBeUndefined();
    expect(state).toBe("running");
  });

});
