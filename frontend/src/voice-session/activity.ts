export const voiceActivity = { level: 0 };

let decayTimer: number | null = null;

export function updateVoiceActivity(level: number): void {
  voiceActivity.level = Math.max(0, Math.min(1, level));
  if (typeof window === "undefined") return;
  if (decayTimer !== null) window.clearTimeout(decayTimer);
  decayTimer = window.setTimeout(() => {
    voiceActivity.level = 0;
    decayTimer = null;
  }, 180);
}

export function clearVoiceActivity(): void {
  voiceActivity.level = 0;
  if (typeof window !== "undefined" && decayTimer !== null) {
    window.clearTimeout(decayTimer);
  }
  decayTimer = null;
}
