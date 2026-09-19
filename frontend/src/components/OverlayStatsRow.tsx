type Stat = {
  label: string;
  value: string | number;
};

type FocusItem = {
  label: string;
  fraction: number;
};

type OverlayStatsRowProps = {
  stats: Stat[];
  focus?: FocusItem;
};

// Shared "informacoes ativas" style stat-chip row, reused by the Missions and
// Auditoria overlays (docs/CREATOR_INTERFACE_FROZEN_SPEC.md-compliant: this only
// ever renders inside an already-open on-demand overlay, never standalone/fixed).
export function OverlayStatsRow({ stats, focus }: OverlayStatsRowProps) {
  return (
    <section className="overlay-stats-row" aria-label="Resumo">
      <div className="overlay-stats-chips">
        {stats.map((stat) => (
          <div className="overlay-stat-chip" key={stat.label}>
            <strong>{stat.value}</strong>
            <span>{stat.label}</span>
          </div>
        ))}
      </div>
      {focus ? (
        <div className="overlay-stat-focus">
          <span>{focus.label}</span>
          <div className="overlay-stat-focus-track">
            <div className="overlay-stat-focus-fill" style={{ width: `${Math.round(focus.fraction * 100)}%` }} />
          </div>
          <strong>{Math.round(focus.fraction * 100)}%</strong>
        </div>
      ) : null}
    </section>
  );
}
