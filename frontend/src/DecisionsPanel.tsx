import { useCallback, useEffect, useState } from "react";
import { decideInception, fetchInceptions, startMission } from "./api";
import type { Inception } from "./api";
import type { MissionView } from "./types";

type Props = {
  missions: MissionView[];
  onChanged: () => void;
};

type Pending = { kind: "approve" | "reject" | "authorize"; id: string } | null;

const AWAITING = ["proposed", "awaiting_creator_decision"];

function errorText(failure: unknown): string {
  const message = failure instanceof Error ? failure.message : "";
  if (message === "AUTH_REQUIRED") return "Session expired. Sign in again.";
  if (message === "HTTP_409" || message === "HTTP_422") return "That transition is no longer allowed. State was refreshed.";
  if (message === "HTTP_403") return "Only the Creator can decide this.";
  return "Action failed. Nothing was changed.";
}

export function DecisionsPanel({ missions, onChanged }: Props) {
  const [inceptions, setInceptions] = useState<Inception[] | null>(null);
  const [confirming, setConfirming] = useState<Pending>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setInceptions(await fetchInceptions());
    } catch {
      setInceptions(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const waiting = (inceptions ?? []).filter((inception) => AWAITING.includes(inception.status));
  const validated = missions.filter((mission) => mission.status === "validated");

  async function run(action: NonNullable<Pending>) {
    setBusy(action.id);
    setError(null);
    try {
      if (action.kind === "authorize") await startMission(action.id);
      else await decideInception(action.id, action.kind);
      setConfirming(null);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(null);
      await refresh();
      onChanged();
    }
  }

  return (
    <aside className="decisions-panel" aria-label="Creator decisions">
      <div className="panel-title">DECISIONS</div>
      {inceptions === null && <div className="empty">Inception list unavailable.</div>}
      <div className="stack" aria-live="polite">
        {waiting.map((inception) => (
          <div className="decision" key={inception.id}>
            <div><strong>{inception.title}</strong><small>{inception.description}</small></div>
            {confirming?.id === inception.id ? (
              <div className="decision-confirm">
                <button type="button" className="decision-go" disabled={busy === inception.id} onClick={() => void run(confirming)}>Confirm {confirming.kind}</button>
                <button type="button" disabled={busy === inception.id} onClick={() => setConfirming(null)}>Cancel</button>
              </div>
            ) : (
              <div className="decision-actions">
                <button type="button" onClick={() => setConfirming({ kind: "approve", id: inception.id })}>Approve</button>
                <button type="button" onClick={() => setConfirming({ kind: "reject", id: inception.id })}>Reject</button>
              </div>
            )}
          </div>
        ))}
        {validated.map((mission) => (
          <div className="decision" key={mission.id}>
            <div><strong>{mission.title}</strong><small>Validated mission awaiting authorization</small></div>
            {confirming?.id === mission.id ? (
              <div className="decision-confirm">
                <button type="button" className="decision-go" disabled={busy === mission.id} onClick={() => void run(confirming)}>Confirm authorize</button>
                <button type="button" disabled={busy === mission.id} onClick={() => setConfirming(null)}>Cancel</button>
              </div>
            ) : (
              <div className="decision-actions">
                <button type="button" onClick={() => setConfirming({ kind: "authorize", id: mission.id })}>Authorize</button>
              </div>
            )}
          </div>
        ))}
        {inceptions !== null && !waiting.length && !validated.length && <div className="empty">Nothing is waiting for the Creator.</div>}
      </div>
      {error && <div className="console-error" role="alert">{error}</div>}
    </aside>
  );
}
