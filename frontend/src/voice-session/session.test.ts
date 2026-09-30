import { describe, expect, it } from "vitest";

import { VoiceSessionModel } from "./session";

describe("VoiceSessionModel", () => {
  it("enters armed state from the authenticated session_ready event", () => {
    const model = new VoiceSessionModel();

    model.onServerEvent({
      type: "session_ready",
      session_id: "session-1",
      turn_id: 0,
      state: "ARMED",
    });

    expect(model.sessionId).toBe("session-1");
    expect(model.turnId).toBe(0);
    expect(model.state).toBe("armed");
  });

  it("ignores stale events from a cancelled or older turn", () => {
    const model = new VoiceSessionModel();
    model.onServerEvent({
      type: "session_ready",
      session_id: "session-1",
      turn_id: 0,
      state: "ARMED",
    });
    model.onServerEvent({
      type: "state",
      session_id: "session-1",
      turn_id: 2,
      state: "SPEAKING",
    });
    model.onServerEvent({
      type: "state",
      session_id: "session-1",
      turn_id: 1,
      state: "THINKING",
    });

    expect(model.turnId).toBe(2);
    expect(model.state).toBe("speaking");
  });

  it("creates a barge_in event only for the active speaking turn", () => {
    const model = new VoiceSessionModel();
    model.onServerEvent({
      type: "session_ready",
      session_id: "session-1",
      turn_id: 0,
      state: "ARMED",
    });
    model.onServerEvent({
      type: "state",
      session_id: "session-1",
      turn_id: 3,
      state: "SPEAKING",
    });

    expect(model.bargeIn()).toEqual({
      type: "barge_in",
      session_id: "session-1",
      turn_id: 3,
    });

    model.onServerEvent({
      type: "state",
      session_id: "session-1",
      turn_id: 3,
      state: "LISTENING",
    });
    expect(model.bargeIn()).toBeNull();
  });

  it("enters reconnecting on socket loss without accepting stale session events", () => {
    const model = new VoiceSessionModel();
    model.onServerEvent({
      type: "session_ready",
      session_id: "session-1",
      turn_id: 0,
      state: "ARMED",
    });
    model.onSocketClosed();

    expect(model.state).toBe("reconnecting");

    model.onServerEvent({
      type: "state",
      session_id: "session-1",
      turn_id: 1,
      state: "SPEAKING",
    });
    expect(model.state).toBe("reconnecting");

    model.onServerEvent({
      type: "session_ready",
      session_id: "session-2",
      turn_id: 0,
      state: "ARMED",
    });
    expect(model.sessionId).toBe("session-2");
    expect(model.state).toBe("armed");
  });
});
