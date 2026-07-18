import { FormEvent, ReactNode, useState } from "react";
import type { ChatItem } from "../types";

type LivingDashboardProps = {
  authenticated: boolean;
  busy: boolean;
  authError: string | null;
  message: string;
  chat: ChatItem[];
  demandPanel: ReactNode;
  onMessage: (value: string) => void;
  onSend: (event: FormEvent) => void;
};

type Hotspot = {
  id: string;
  label: string;
  xPercent: number;
  yPercent: number;
  radiusPercent: number;
  tone: "gold" | "violet" | "blue" | "green" | "red";
};

const APPROVED_UNIVERSE_SRC = "/creator-interface-approved-universe.png";

const universeHotspots: Hotspot[] = [
  { id: "deus", label: "DEUS", xPercent: 50.2, yPercent: 50.9, radiusPercent: 5.8, tone: "gold" },
  { id: "sophia", label: "SOPHIA", xPercent: 39.6, yPercent: 48.5, radiusPercent: 4.6, tone: "violet" },
  { id: "rockmam", label: "ROCKMAM", xPercent: 62.8, yPercent: 51.5, radiusPercent: 4.4, tone: "gold" },
  { id: "eng", label: "ENG", xPercent: 21.4, yPercent: 51.8, radiusPercent: 3.4, tone: "blue" },
  { id: "jur", label: "JUR", xPercent: 27.4, yPercent: 78.8, radiusPercent: 3.2, tone: "green" },
  { id: "fin", label: "FIN", xPercent: 79.5, yPercent: 47.7, radiusPercent: 3.6, tone: "green" },
  { id: "seg", label: "SEG", xPercent: 69.2, yPercent: 75.4, radiusPercent: 3.2, tone: "red" },
  { id: "neg", label: "NEG", xPercent: 76.6, yPercent: 19.6, radiusPercent: 3.5, tone: "gold" },
  { id: "cie", label: "CIE", xPercent: 48.8, yPercent: 16.8, radiusPercent: 3.4, tone: "blue" },
  { id: "con", label: "CON", xPercent: 24.2, yPercent: 27.0, radiusPercent: 3.4, tone: "violet" },
  { id: "cri", label: "CRI", xPercent: 48.3, yPercent: 83.5, radiusPercent: 3.2, tone: "gold" },
];

function FrozenUniverseBackground() {
  const [available, setAvailable] = useState(true);

  return (
    <>
      {available ? (
        <img
          className="frozen-universe-background"
          src={APPROVED_UNIVERSE_SRC}
          alt=""
          aria-hidden="true"
          draggable={false}
          onError={() => setAvailable(false)}
        />
      ) : null}
    </>
  );
}

function UniverseInteractionLayer() {
  const [active, setActive] = useState<Hotspot | null>(null);

  return (
    <section className="universe-interaction-layer" aria-label="Nucleos do universo vivo">
      {universeHotspots.map((hotspot) => (
        <button
          key={hotspot.id}
          type="button"
          className={`universe-hotspot tone-${hotspot.tone}`}
          style={
            {
              "--hotspot-x": `${hotspot.xPercent}%`,
              "--hotspot-y": `${hotspot.yPercent}%`,
              "--hotspot-r": `${hotspot.radiusPercent}vw`,
            } as React.CSSProperties
          }
          aria-label={hotspot.label}
          onMouseEnter={() => setActive(hotspot)}
          onMouseLeave={() => setActive(null)}
          onFocus={() => setActive(hotspot)}
          onBlur={() => setActive(null)}
        />
      ))}
      {active ? (
        <span
          className={`hotspot-tooltip tone-${active.tone}`}
          style={
            {
              "--tooltip-x": `${active.xPercent}%`,
              "--tooltip-y": `${active.yPercent}%`,
            } as React.CSSProperties
          }
        >
          {active.label}
        </span>
      ) : null}
    </section>
  );
}

function ConversationDock({
  authenticated,
  busy,
  message,
  onMessage,
  onSend,
}: Pick<LivingDashboardProps, "authenticated" | "busy" | "message" | "onMessage" | "onSend">) {
  return (
    <form className="conversation-dock" onSubmit={onSend} aria-label="Conversa com DEUS">
      <span className={`dock-processing-dot ${busy ? "is-processing" : ""}`} aria-hidden="true" />
      <input
        value={message}
        onChange={(event) => onMessage(event.target.value)}
        placeholder="Fale com DEUS..."
        aria-label="Fale com DEUS"
        disabled={busy || !authenticated}
      />
      <button className="dock-microphone" type="button" aria-label="Microfone" disabled={!authenticated}>
        <span aria-hidden="true" />
      </button>
      <button className="dock-send" type="submit" aria-label="Enviar mensagem" disabled={busy || !authenticated || !message.trim()}>
        <span aria-hidden="true">Enviar</span>
      </button>
    </form>
  );
}

function TransientNotificationLayer({ chat, busy, authError }: Pick<LivingDashboardProps, "chat" | "busy" | "authError">) {
  const latest = [...chat].reverse().find((item) => item.role !== "creator");

  if (authError) {
    return (
      <section className="transient-response" aria-live="polite">
        <span>DEUS</span>
        <p>Conexao com o nucleo temporariamente indisponivel.</p>
      </section>
    );
  }

  if (busy) {
    return (
      <section className="transient-response" aria-live="polite">
        <span>DEUS</span>
        <p>Percebendo.</p>
      </section>
    );
  }

  if (!latest || latest.id === "intro") return null;

  return (
    <section className="transient-response" aria-live="polite">
      <span>{latest.role === "trinity" ? "TRINDADE" : "DEUS"}</span>
      <p>{latest.text}</p>
    </section>
  );
}

export function LivingDashboard({
  authenticated,
  busy,
  authError,
  message,
  chat,
  demandPanel,
  onMessage,
  onSend,
}: LivingDashboardProps) {
  return (
    <main className="creator-interface-frozen" data-authenticated={authenticated}>
      <FrozenUniverseBackground />
      <UniverseInteractionLayer />
      <TransientNotificationLayer chat={chat} busy={busy} authError={authError} />
      <ConversationDock authenticated={authenticated} busy={busy} message={message} onMessage={onMessage} onSend={onSend} />
      <section className="on-demand-overlay-host" aria-label="Overlay sob demanda">
        {demandPanel}
      </section>
    </main>
  );
}
