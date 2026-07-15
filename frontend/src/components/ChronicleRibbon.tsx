import type { ChronicleEntry } from "../types";

type ChronicleRibbonProps = {
  entries: ChronicleEntry[];
  loading: boolean;
};

export function ChronicleRibbon({ entries, loading }: ChronicleRibbonProps) {
  return (
    <footer className="chronicle-ribbon">
      <div className="chronicle-track">
        {loading ? <span>Loading Chronicle...</span> : null}
        {!loading && entries.length === 0 ? <span>No Chronicle entries returned by the backend.</span> : null}
        {entries.map((entry) => (
          <span key={entry.id}>
            <strong>#{entry.position} {entry.actor_role}</strong>
            {entry.event_type} / {entry.aggregate_type}
          </span>
        ))}
      </div>
    </footer>
  );
}
