import type { Inception } from "../types";

type InceptionPanelProps = {
  inceptions: Inception[];
  loading?: boolean;
  error?: string | null;
  onSubmit?: (id: string) => void;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onCreateMission?: (item: Inception) => void;
};

export function InceptionPanel({
  inceptions,
  loading = false,
  error = null,
  onSubmit,
  onApprove,
  onReject,
  onCreateMission,
}: InceptionPanelProps) {
  return (
    <aside className="inception-panel">
      <header>
        <strong>INCEPTIONS PENDENTES</strong>
        <span>{inceptions.length}</span>
      </header>
      {inceptions.length === 0 ? (
        <article>
          <strong>API</strong>
          <span>Sem pendencias</span>
          <p>Nenhuma Inception pendente retornada.</p>
        </article>
      ) : null}
      {inceptions.slice(0, 4).map((item) => (
        <article key={item.id} data-source="API">
          <strong>{item.id.startsWith("INC-") ? item.id : `INC-${item.id.slice(0, 4)}`}</strong>
          <span>{item.status}</span>
          <p>{item.title}</p>
          <div className="inception-actions">
            {item.status === "proposed" ? (
              <button type="button" disabled={loading} onClick={() => onSubmit?.(item.id)}>
                Enviar
              </button>
            ) : null}
            {item.status === "awaiting_creator_decision" ? (
              <>
                <button type="button" disabled={loading} onClick={() => onApprove?.(item.id)}>
                  Aprovar
                </button>
                <button type="button" disabled={loading} onClick={() => onReject?.(item.id)}>
                  Negar
                </button>
              </>
            ) : null}
            {item.status === "approved" ? (
              <button type="button" disabled={loading} onClick={() => onCreateMission?.(item)}>
                Criar missao
              </button>
            ) : null}
          </div>
        </article>
      ))}
      {error ? <p className="inception-error">{error}</p> : null}
    </aside>
  );
}
