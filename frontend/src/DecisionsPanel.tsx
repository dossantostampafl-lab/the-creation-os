import { useState } from "react";
import { authorizeMission, decideInception } from "./api";
import type { InceptionView } from "./api";
import type { MissionView } from "./types";

type Props = {
  inceptions: InceptionView[] | null;
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

export function DecisionsPanel({ inceptions, missions, onChanged }: Props) {
  const [confirming, setConfirming] = useState<Pending>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const waiting = (inceptions ?? []).filter((inception) => AWAITING.includes(inception.status));
  const validated = missions.filter((mission) => mission.status === "validated");

  async function run(action: NonNullable<Pending>) {
    setBusy(action.id);
    setError(null);
    try {
      if (action.kind === "authorize") await authorizeMission(action.id);
      else await decideInception(action.id, action.kind, reason);
      setConfirming(null);
      setReason("");
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(null);
      onChanged();
    }
  }

  const startInception = (kind: "approve" | "reject", id: string) => {
    setConfirming({ kind, id });
    setReason("");
  };

  return (
    <article className="panel decisions-panel">
      <div className="panel-title">DECISIONS</div>
      {inceptions === null && <div className="empty">Inception list unavailable.</div>}
      <div className="stack" aria-live="polite">
        {waiting.map((inception) => (
          <div className="decision" key={inception.id}>
            <div><strong>{inception.title}</strong><small>{inception.description}</small></div>
            {confirming && confirming.id === inception.id && confirming.kind !== "authorize" ? (
              <div className="decision-confirm">
                <input aria-label="Reason (optional)" placeholder="Reason (optional)" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
                <button type="button" className="decision-go" disabled={busy === inception.id} onClick={() => void run(confirming)}>Confirm {confirming.kind}</button>
                <button type="button" disabled={busy === inception.id} onClick={() => setConfirming(null)}>Cancel</button>
              </div>
            ) : (
              <div className="decision-actions">
                <button type="button" onClick={() => startInception("approve", inception.id)}>Approve</button>
                <button type="button" onClick={() => startInception("reject", inception.id)}>Reject</button>
              </div>
            )}
          </div>
        ))}
        {validated.map((mission) => (
          <div className="decision" key={mission.id}>
            <div><strong>{mission.title}</strong><small>Validated mission awaiting authorization</small></div>
            {confirming && confirming.id === mission.id && confirming.kind === "authorize" ? (
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
    </article>
  );
}
