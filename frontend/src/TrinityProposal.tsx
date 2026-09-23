import type { Inception } from "./api";

type Props = {
  inception: Inception;
  busy: boolean;
  onDecide: (decision: "approve" | "reject") => void;
};

const DECIDED: Record<string, string> = { approved: "Approved", rejected: "Rejected", cancelled: "Cancelled" };

/** A Mission proposed by SOPHIA and ROCKMAM, waiting for the Creator's word. */
export function TrinityProposal({ inception, busy, onDecide }: Props) {
  const { sophia, rockmam, mission_plan: plan, verdict } = inception.trinity_assessment;
  const awaiting = inception.status === "awaiting_creator_decision";
  const steps = [...(plan?.steps ?? [])].sort((a, b) => a.position - b.position);

  return (
    <article className="trinity-proposal" aria-label={`Trinity proposal: ${inception.title}`}>
      <header>
        <span>TRINITY PROPOSAL</span>
        {verdict && (
          <b className={`verdict ${verdict.result === "VIABLE" ? "viable" : "needs-creator"}`}>
            {verdict.result === "VIABLE" ? "Viable" : `Needs ${verdict.unavailable_universes.join(", ")}`}
          </b>
        )}
      </header>
      <h3>{inception.title}</h3>
      <p className="objective">{rockmam?.objective ?? inception.description}</p>
      <div className="proposal-body">
        {sophia && (
          <section>
            <h4>SOPHIA</h4>
            <p>{sophia.recommendation}</p>
            {sophia.risks.length > 0 && <p className="risks">Risks: {sophia.risks.join(" · ")}</p>}
          </section>
        )}
        {steps.length > 0 && (
          <section>
            <h4>ROCKMAM</h4>
            <ol>
              {steps.map((step) => (
                <li key={step.step_key}>{step.title} <em>{step.universe}</em></li>
              ))}
            </ol>
          </section>
        )}
      </div>
      {awaiting ? (
        <div className="proposal-actions">
          <button type="button" className="approve" disabled={busy} onClick={() => onDecide("approve")}>Approve</button>
          <button type="button" className="reject" disabled={busy} onClick={() => onDecide("reject")}>Reject</button>
        </div>
      ) : (
        <p className={`decided ${inception.status}`}>{DECIDED[inception.status] ?? inception.status}</p>
      )}
    </article>
  );
}
