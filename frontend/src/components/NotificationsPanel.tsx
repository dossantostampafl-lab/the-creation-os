import type { CreatorNotification } from "../types";

type NotificationsPanelProps = {
  notifications: CreatorNotification[];
  onReadNotification: (id: string) => void;
};

function compactDate(value: string) {
  return new Date(value).toLocaleString("pt-BR");
}

export function NotificationsPanel({ notifications, onReadNotification }: NotificationsPanelProps) {
  const sorted = [...notifications].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  const unreadCount = notifications.filter((item) => item.status === "unread").length;

  return (
    <section className="notifications-panel" aria-label="Notificacoes">
      <header>
        <strong>NOTIFICACOES</strong>
        <span>{unreadCount} nao lida{unreadCount === 1 ? "" : "s"}</span>
      </header>
      {sorted.length === 0 ? <p className="notifications-muted">Nenhuma notificacao retornada pela API.</p> : null}
      {sorted.map((notification) => (
        <article key={notification.id} className={notification.status === "unread" ? "is-unread" : undefined}>
          <div className="notifications-title">
            <strong>{notification.title}</strong>
            <span>{notification.type}</span>
          </div>
          <p>{notification.message}</p>
          <div className="notifications-meta">
            <span>{compactDate(notification.created_at)}</span>
            {notification.status === "unread" ? (
              <button type="button" onClick={() => onReadNotification(notification.id)}>
                Marcar como lida
              </button>
            ) : (
              <span className="notifications-read-tag">lida</span>
            )}
          </div>
        </article>
      ))}
    </section>
  );
}
