import type { Opportunity } from "../types";

type OpportunityPanelProps = {
  opportunities: Opportunity[];
  loading: boolean;
  error: string | null;
  onDiscover: () => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onConvert: (id: string) => void;
};

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function OpportunityPanel({
  opportunities,
  loading,
  error,
  onDiscover,
  onApprove,
  onReject,
  onConvert,
}: OpportunityPanelProps) {
  const selected = opportunities[0] ?? null;

  return (
    <section className="opportunity-panel" aria-label="Oportunidades">
      <header>
        <strong>OPORTUNIDADES</strong>
        <button type="button" disabled={loading} onClick={onDiscover}>
          Descobrir
        </button>
      </header>
      {loading ? <p className="opportunity-muted">Analisando observacoes...</p> : null}
      {!loading && opportunities.length === 0 ? <p className="opportunity-muted">Nenhuma oportunidade detectada.</p> : null}
      {opportunities.slice(0, 3).map((item) => (
        <article key={item.id}>
          <div className="opportunity-title">
            <strong>{item.title}</strong>
            <span>
              {item.universe} · {item.status}
            </span>
          </div>
          <div className="opportunity-score">
            <strong>{percent(item.priority_score)}</strong>
            <span>score</span>
          </div>
          <p>{item.summary}</p>
          <dl>
            <div>
              <dt>Conf.</dt>
              <dd>{percent(item.confidence)}</dd>
            </div>
            <div>
              <dt>Impacto</dt>
              <dd>{percent(item.impact)}</dd>
            </div>
            <div>
              <dt>Urg.</dt>
              <dd>{percent(item.urgency)}</dd>
            </div>
            <div>
              <dt>Risco</dt>
              <dd>{percent(item.risk)}</dd>
            </div>
          </dl>
          <div className="opportunity-actions">
            <button
              type="button"
              disabled={loading || item.status !== "pending_creator_review"}
              onClick={() => window.confirm("Aprovar esta oportunidade?") && onApprove(item.id)}
            >
              Aprovar
            </button>
            <button
              type="button"
              disabled={loading || item.status !== "pending_creator_review"}
              onClick={() => onReject(item.id)}
            >
              Rejeitar
            </button>
            <button
              type="button"
              disabled={loading || item.status !== "approved"}
              onClick={() => window.confirm("Converter oportunidade aprovada em Inception?") && onConvert(item.id)}
            >
              Inception
            </button>
          </div>
        </article>
      ))}
      {selected ? (
        <footer>
          <strong>Explicacao</strong>
          <p>{selected.explanation}</p>
          <span>
            Evidencias: {selected.evidence.observations?.length ?? 0} · Validade:{" "}
            {new Date(selected.expires_at).toLocaleString()}
          </span>
        </footer>
      ) : null}
      {error ? <p className="opportunity-error">{error}</p> : null}
    </section>
  );
}
