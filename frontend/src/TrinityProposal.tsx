import type { Inception, Mission } from "./api";

export type Proposal = { inception: Inception; mission: Mission | null };
export type ProposalAction = "start" | "cancel" | "dismiss";

type Props = {
  proposal: Proposal;
  busy: boolean;
  onAct: (action: ProposalAction) => void;
};

const READY = new Set(["validated", "authorized", "distributed"]);

const BLOCKER_TEXT = {
  inactive: "is not active",
  no_active_agent: "has no active Agent",
  unknown: "does not exist yet",
} as const;

const OUTCOME: Record<string, string> = {
  executing: "Executing",
  manifested: "Manifested",
  failed: "Failed",
  cancelled: "Cancelled",
  rejected: "Dismissed",
  approved: "Approved",
};

/** What the Creator can do with a proposal right now. */
export function proposalStage(proposal: Proposal): "ready" | "blocked" | "settled" {
  if (proposal.mission) return READY.has(proposal.mission.status) ? "ready" : "settled";
  const blocked = proposal.inception.status === "awaiting_creator_decision"
    && proposal.inception.trinity_assessment.verdict?.result === "REQUIRES_CREATOR";
  return blocked ? "blocked" : "settled";
}

const HEADING = { ready: "MISSION READY", blocked: "NOT VIABLE YET", settled: "TRINITY MISSION" } as const;

/** A Mission shaped by SOPHIA and ROCKMAM: ready to start on the Creator's word, or blocked with the reason. */
export function TrinityProposal({ proposal, busy, onAct }: Props) {
  const { inception, mission } = proposal;
  const { sophia, rockmam, mission_plan: plan, verdict } = inception.trinity_assessment;
  const stage = proposalStage(proposal);
  const steps = [...(plan?.steps ?? [])].sort((a, b) => a.position - b.position);

  return (
    <article className={`trinity-proposal ${stage}`} aria-label={`Trinity proposal: ${inception.title}`}>
      <header>
        <span>{HEADING[stage]}</span>
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
      {stage === "blocked" && (verdict?.blockers ?? []).length > 0 && (
        <ul className="blockers">
          {(verdict?.blockers ?? []).map((blocker) => (
            <li key={blocker.universe}>Universe {blocker.universe} {BLOCKER_TEXT[blocker.reason]}</li>
          ))}
        </ul>
      )}
      {stage === "ready" && (
        <div className="proposal-actions">
          <button type="button" className="approve" disabled={busy} onClick={() => onAct("start")}>Authorize &amp; start</button>
          <button type="button" className="reject" disabled={busy} onClick={() => onAct("cancel")}>Cancel</button>
        </div>
      )}
      {stage === "blocked" && (
        <div className="proposal-actions">
          <button type="button" className="reject" disabled={busy} onClick={() => onAct("dismiss")}>Dismiss</button>
        </div>
      )}
      {stage === "settled" && (
        <p className={`decided ${mission?.status ?? inception.status}`}>
          {OUTCOME[mission?.status ?? inception.status] ?? mission?.status ?? inception.status}
        </p>
      )}
    </article>
  );
}
