import { FormEvent } from "react";
import { ArrowRight, Lock } from "lucide-react";

type GodChatProps = {
  authenticated: boolean;
  busy: boolean;
  message: string;
  username: string;
  password: string;
  onMessage: (value: string) => void;
  onUsername: (value: string) => void;
  onPassword: (value: string) => void;
  onSend: (event: FormEvent) => void;
  onLogin: (event: FormEvent) => void;
  error?: string | null;
  devPassword?: string;
};

export function GodChat({
  authenticated,
  busy,
  message,
  username,
  password,
  onMessage,
  onUsername,
  onPassword,
  onSend,
  onLogin,
  error,
  devPassword,
}: GodChatProps) {
  if (!authenticated) {
    return (
      <div className="creator-login-shell">
        <form className="god-chat exact-chat locked-chat creator-login-form" onSubmit={onLogin}>
          <Lock size={16} />
          <input
            type="text"
            value={username}
            onChange={(event) => onUsername(event.target.value)}
            placeholder="Criador"
            autoComplete="username"
          />
          <input
            type="password"
            value={password}
            onChange={(event) => onPassword(event.target.value)}
            placeholder="Senha do Criador"
            autoComplete="current-password"
          />
          <button disabled={busy || !username.trim() || !password.trim()} type="submit" aria-label="Autenticar Criador">
            <ArrowRight size={22} />
          </button>
        </form>
        {devPassword ? (
          <button className="creator-dev-password" type="button" onClick={() => onPassword(devPassword)}>
            Usar senha local de desenvolvimento
          </button>
        ) : null}
        {error ? <p className="creator-login-error">{error}</p> : null}
      </div>
    );
  }

  return (
    <form className="god-chat exact-chat" onSubmit={onSend}>
      <input
        disabled={busy}
        value={message}
        onChange={(event) => onMessage(event.target.value)}
        placeholder="Fale com DEUS..."
      />
      <button disabled={busy || !message.trim()} type="submit" aria-label="Enviar para DEUS">
        <ArrowRight size={22} />
      </button>
    </form>
  );
}
