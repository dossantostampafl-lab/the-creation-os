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
