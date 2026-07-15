import { Activity, Shield } from "lucide-react";
import type { Pulse } from "../types";

type PulseHeaderProps = {
  pulse: Pulse | null;
  loadState: string;
  authenticated: boolean;
  activeAgents: number;
  refreshSeconds: number;
};

export function PulseHeader({ pulse, loadState, authenticated, activeAgents, refreshSeconds }: PulseHeaderProps) {
  const status = pulse?.status ?? (authenticated ? loadState : "locked");
  const degraded = status === "degraded" || loadState === "error";

  return (
    <header className="pulse-header">
      <div className="pulse-status">
        <span className={`pulse-beacon ${degraded ? "degraded" : ""}`} />
        <strong>Pulse</strong>
        <span>{status}</span>
      </div>
      <div className="pulse-metrics">
        <span><Activity size={14} /> {pulse?.active_universes ?? 0} universes</span>
        <span>{pulse?.active_agents ?? activeAgents} agents</span>
        <span>{pulse?.running_missions ?? 0} missions</span>
        <span>refresh {refreshSeconds}s</span>
      </div>
      <div className="pulse-integrity">
        <Shield size={14} />
        {pulse?.chronicles_chain.valid === false ? "chronicle degraded" : "chronicle verified"}
      </div>
    </header>
  );
}
