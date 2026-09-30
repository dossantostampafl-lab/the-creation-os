import { describe, expect, it } from "vitest";

import { VoiceActivityDetector, rms } from "./vad";

describe("voice activity detection", () => {
  it("computes RMS loudness for mono PCM frames", () => {
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5, 6);
  });

  it("enters speaking above threshold and requires quiet hysteresis to release", () => {
    const detector = new VoiceActivityDetector({
      threshold: 0.05,
      releaseFrames: 2,
    });

    expect(detector.update(new Float32Array([0.1, -0.1]))).toBe(true);
    expect(detector.update(new Float32Array([0.01, -0.01]))).toBe(true);
    expect(detector.update(new Float32Array([0.01, -0.01]))).toBe(false);
  });

  it("does not enter speaking for low-level background noise", () => {
    const detector = new VoiceActivityDetector({
      threshold: 0.05,
      releaseFrames: 2,
    });

    expect(detector.update(new Float32Array([0.01, -0.02, 0.01]))).toBe(false);
  });
});
