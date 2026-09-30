export function rms(samples: Float32Array): number {
  if (!samples.length) return 0;
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.sqrt(sum / samples.length);
}

export type VoiceActivityDetectorOptions = {
  threshold: number;
  releaseFrames: number;
};

export class VoiceActivityDetector {
  private speaking = false;
  private quietFrames = 0;

  constructor(private readonly options: VoiceActivityDetectorOptions) {
    if (!(options.threshold > 0 && options.threshold <= 1)) {
      throw new Error("VOICE_VAD_INVALID_THRESHOLD");
    }
    if (!Number.isInteger(options.releaseFrames) || options.releaseFrames < 1) {
      throw new Error("VOICE_VAD_INVALID_RELEASE_FRAMES");
    }
  }

  update(samples: Float32Array): boolean {
    const level = rms(samples);

    if (level >= this.options.threshold) {
      this.speaking = true;
      this.quietFrames = 0;
      return true;
    }

    if (!this.speaking) return false;

    this.quietFrames += 1;
    if (this.quietFrames >= this.options.releaseFrames) {
      this.speaking = false;
      this.quietFrames = 0;
    }

    return this.speaking;
  }

  reset(): void {
    this.speaking = false;
    this.quietFrames = 0;
  }
}
