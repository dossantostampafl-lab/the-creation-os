import { FormEvent } from "react";
import { Lock, Send, User } from "lucide-react";
import type { ChatItem } from "../types";

type GodDockProps = {
  authenticated: boolean;
  busy: boolean;
  username: string;
  password: string;
  message: string;
  chat: ChatItem[];
  notice: string | null;
  onUsername: (value: string) => void;
  onPassword: (value: string) => void;
  onMessage: (value: string) => void;
  onLogin: (event: FormEvent) => void;
  onSend: (event: FormEvent) => void;
  onLogout: () => void;
};

export function GodDock({
  authenticated,
  busy,
  username,
  password,
  message,
  chat,
  notice,
  onUsername,
  onPassword,
  onMessage,
  onLogin,
  onSend,
  onLogout,
}: GodDockProps) {
  const latest = chat.slice(-3);

  return (
    <aside className="god-dock">
      <div className="god-transcript">
        {latest.map((item) => (
          <article key={item.id} className={`transmission ${item.role}`}>
            <span>{item.meta ?? item.role}</span>
            <p>{item.text}</p>
          </article>
        ))}
      </div>

      {authenticated ? (
        <form className="god-input" onSubmit={onSend}>
          <input
            disabled={busy}
            value={message}
            onChange={(event) => onMessage(event.target.value)}
            placeholder="Speak to GOD"
          />
          <button disabled={busy || !message.trim()} type="submit" aria-label="Send to GOD">
            <Send size={17} />
          </button>
          <button className="lock-button" type="button" onClick={onLogout} aria-label="Lock Creator session">
            <Lock size={16} />
          </button>
        </form>
      ) : (
        <form className="creator-login" onSubmit={onLogin}>
          <label>
            <User size={14} />
            <input value={username} onChange={(event) => onUsername(event.target.value)} placeholder="creator" />
          </label>
          <label>
            <Lock size={14} />
            <input
              type="password"
              value={password}
              onChange={(event) => onPassword(event.target.value)}
              placeholder="password"
            />
          </label>
          <button disabled={busy} type="submit">Enter</button>
        </form>
      )}
      {notice && <small className="dock-notice">{notice}</small>}
    </aside>
  );
}
