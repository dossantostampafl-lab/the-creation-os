import { FormEvent } from "react";
import { ArrowRight, Lock } from "lucide-react";

type GodChatProps = {
  authenticated: boolean;
  busy: boolean;
  message: string;
  password: string;
  onMessage: (value: string) => void;
  onPassword: (value: string) => void;
  onSend: (event: FormEvent) => void;
  onLogin: (event: FormEvent) => void;
};

export function GodChat({ authenticated, busy, message, password, onMessage, onPassword, onSend, onLogin }: GodChatProps) {
  if (!authenticated) {
    return (
      <form className="god-chat exact-chat locked-chat" onSubmit={onLogin}>
        <Lock size={16} />
        <input
          type="password"
          value={password}
          onChange={(event) => onPassword(event.target.value)}
          placeholder="Autenticar Criador..."
        />
        <button disabled={busy} type="submit" aria-label="Autenticar Criador">
          <ArrowRight size={22} />
        </button>
      </form>
    );
  }

  return (
    <form className="god-chat exact-chat" onSubmit={onSend}>
      <input
        disabled={busy}
        value={message}
        onChange={(event) => onMessage(event.target.value)}
        placeholder="Fale com GOD..."
      />
      <button disabled={busy || !message.trim()} type="submit" aria-label="Enviar para GOD">
        <ArrowRight size={22} />
      </button>
    </form>
  );
}
