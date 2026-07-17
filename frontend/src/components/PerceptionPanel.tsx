import type { CreatorNotification, PerceptionSource } from "../types";

type PerceptionPanelProps = {
  sources: PerceptionSource[];
  notifications: CreatorNotification[];
  loading: boolean;
  error: string | null;
  onEnable: (id: string) => void;
  onDisable: (id: string) => void;
  onRun: (id: string) => void;
  onReadNotification: (id: string) => void;
};

function compactDate(value: string | null) {
  if (!value) return "nunca";
  return new Date(value).toLocaleTimeString();
}

export function PerceptionPanel({
  sources,
  notifications,
  loading,
  error,
  onEnable,
  onDisable,
  onRun,
  onReadNotification,
}: PerceptionPanelProps) {
  const unread = notifications.filter((item) => item.status === "unread");

  return (
    <section className="perception-panel" aria-label="Percepcao">
      <header>
        <strong>PERCEPCAO</strong>
        <span>{unread.length}</span>
      </header>
      {loading ? <p className="perception-muted">Atualizando fontes...</p> : null}
      {!loading && sources.length === 0 ? <p className="perception-muted">Nenhuma fonte configurada.</p> : null}
      {sources.slice(0, 3).map((source) => (
        <article key={source.id}>
          <div className="perception-source">
            <strong>{source.name}</strong>
            <span>
              {source.universe} / {source.provider}
            </span>
          </div>
          <dl>
            <div>
              <dt>Estado</dt>
              <dd>{source.state}</dd>
            </div>
            <div>
              <dt>Ultima</dt>
              <dd>{compactDate(source.last_succeeded_at)}</dd>
            </div>
            <div>
              <dt>Falhas</dt>
              <dd>{source.failure_count}</dd>
            </div>
          </dl>
          <div className="perception-actions">
            <button type="button" disabled={loading} onClick={() => (source.enabled ? onDisable(source.id) : onEnable(source.id))}>
              {source.enabled ? "Desativar" : "Ativar"}
            </button>
            <button type="button" disabled={loading || !source.enabled} onClick={() => onRun(source.id)}>
              Executar
            </button>
          </div>
        </article>
      ))}
      {unread.slice(0, 2).map((notification) => (
        <button className="perception-notification" key={notification.id} type="button" onClick={() => onReadNotification(notification.id)}>
          <strong>{notification.title}</strong>
          <span>{notification.message}</span>
        </button>
      ))}
      {error ? <p className="perception-error">{error}</p> : null}
    </section>
  );
}
