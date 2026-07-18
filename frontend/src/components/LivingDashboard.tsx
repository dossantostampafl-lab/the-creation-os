import { FormEvent, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { ChatItem, CreatorNotification, Pulse } from "../types";
import type { VoiceConversationState } from "../voice";

export type EntityActivityState = "idle" | "active" | "processing" | "waiting" | "completed" | "warning" | "error" | "offline";

export type HotspotSummary = {
  id: string;
  title: string;
  subtitle: string;
  lines: string[];
  actionLabel?: string;
  panel?: "inceptions" | "missions" | "opportunities" | "perception" | "chronicle" | "capabilities" | "universes";
};

type LivingDashboardProps = {
  authenticated: boolean;
  busy: boolean;
  authError: string | null;
  message: string;
  chat: ChatItem[];
  pulse: Pulse | null;
  loadState: "idle" | "loading" | "ready" | "empty" | "error";
  notifications: CreatorNotification[];
  activityStates: Record<string, EntityActivityState>;
  hotspotSummaries: Record<string, HotspotSummary>;
  demandPanel: ReactNode;
  voiceState: VoiceConversationState;
  voiceSupported: boolean;
  voiceError: string | null;
  onMessage: (value: string) => void;
  onSend: (event: FormEvent) => void;
  onVoiceListen: () => void;
  onVoiceStopListening: () => void;
  onVoiceStopSpeaking: () => void;
  onHotspotAction: (summary: HotspotSummary) => void;
  onReadNotification: (notificationId: string) => void;
};

type Hotspot = {
  id: string;
  label: string;
  type: "core" | "universe";
  xPercent: number;
  yPercent: number;
  radiusPercent: number;
  tone: "gold" | "violet" | "blue" | "green" | "red";
};

const APPROVED_UNIVERSE_SRC = "/creator-interface-approved-universe.png";

const universeHotspots: Hotspot[] = [
  { id: "deus", label: "DEUS", type: "core", xPercent: 50.2, yPercent: 50.9, radiusPercent: 5.8, tone: "gold" },
  { id: "sophia", label: "SOPHIA", type: "core", xPercent: 39.6, yPercent: 48.5, radiusPercent: 4.6, tone: "violet" },
  { id: "rockmam", label: "ROCKMAM", type: "core", xPercent: 62.8, yPercent: 51.5, radiusPercent: 4.4, tone: "gold" },
  { id: "eng", label: "ENGENHARIA", type: "universe", xPercent: 21.4, yPercent: 51.8, radiusPercent: 3.4, tone: "blue" },
  { id: "jur", label: "JURIDICO", type: "universe", xPercent: 27.4, yPercent: 78.8, radiusPercent: 3.2, tone: "green" },
  { id: "fin", label: "FINANCAS", type: "universe", xPercent: 79.5, yPercent: 47.7, radiusPercent: 3.6, tone: "green" },
  { id: "seg", label: "SEGURANCA", type: "universe", xPercent: 69.2, yPercent: 75.4, radiusPercent: 3.2, tone: "red" },
  { id: "neg", label: "NEGOCIOS", type: "universe", xPercent: 76.6, yPercent: 19.6, radiusPercent: 3.5, tone: "gold" },
  { id: "cie", label: "CIENCIA", type: "universe", xPercent: 48.8, yPercent: 16.8, radiusPercent: 3.4, tone: "blue" },
  { id: "con", label: "CONHECIMENTO", type: "universe", xPercent: 24.2, yPercent: 27.0, radiusPercent: 3.4, tone: "violet" },
  { id: "cri", label: "CRIACAO", type: "universe", xPercent: 48.3, yPercent: 83.5, radiusPercent: 3.2, tone: "gold" },
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

function UniverseDynamicEffectsLayer({
  activityStates,
}: {
  activityStates: Record<string, EntityActivityState>;
}) {
  return (
    <section className="universe-dynamic-effects-layer" aria-hidden="true">
      {universeHotspots.map((hotspot) => {
        const state = activityStates[hotspot.id] ?? "idle";
        if (state === "idle") return null;
        return (
          <span
            key={hotspot.id}
            className={`entity-activity-glow tone-${hotspot.tone} state-${state}`}
            style={
              {
                "--hotspot-x": `${hotspot.xPercent}%`,
                "--hotspot-y": `${hotspot.yPercent}%`,
                "--hotspot-r": `${hotspot.radiusPercent}vw`,
              } as CSSProperties
            }
          />
        );
      })}
    </section>
  );
}

function UniverseInteractionLayer({
  hotspotSummaries,
  onHotspotAction,
  onFocusConversation,
}: {
  hotspotSummaries: Record<string, HotspotSummary>;
  onHotspotAction: (summary: HotspotSummary) => void;
  onFocusConversation: () => void;
}) {
  const [active, setActive] = useState<Hotspot | null>(null);
  const [selected, setSelected] = useState<Hotspot | null>(null);

  function selectHotspot(hotspot: Hotspot) {
    setSelected(hotspot);
    if (hotspot.id === "deus") onFocusConversation();
  }

  const selectedSummary = selected ? hotspotSummaries[selected.id] : null;

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
            } as CSSProperties
          }
          aria-label={hotspot.label}
          onMouseEnter={() => setActive(hotspot)}
          onMouseLeave={() => setActive(null)}
          onFocus={() => setActive(hotspot)}
          onBlur={() => setActive(null)}
          onClick={() => selectHotspot(hotspot)}
        />
      ))}
      {active ? (
        <span
          className={`hotspot-tooltip tone-${active.tone}`}
          style={
            {
              "--tooltip-x": `${active.xPercent}%`,
              "--tooltip-y": `${active.yPercent}%`,
            } as CSSProperties
          }
        >
          {active.label}
        </span>
      ) : null}
      {selected && selectedSummary ? (
        <aside
          className={`hotspot-popover tone-${selected.tone}`}
          style={
            {
              "--popover-x": `${selected.xPercent}%`,
              "--popover-y": `${selected.yPercent}%`,
            } as CSSProperties
          }
          aria-live="polite"
        >
          <button className="hotspot-popover-close" type="button" aria-label="Fechar resumo" onClick={() => setSelected(null)}>
            Fechar
          </button>
          <span>{selectedSummary.subtitle}</span>
          <strong>{selectedSummary.title}</strong>
          {selectedSummary.lines.map((line) => (
            <p key={line}>{line}</p>
          ))}
          {selectedSummary.actionLabel ? (
            <button type="button" onClick={() => onHotspotAction(selectedSummary)}>
              {selectedSummary.actionLabel}
            </button>
          ) : null}
        </aside>
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
  inputRef,
  voiceState,
  voiceSupported,
  onVoiceListen,
  onVoiceStopListening,
  onVoiceStopSpeaking,
}: Pick<LivingDashboardProps, "authenticated" | "busy" | "message" | "onMessage" | "onSend"> & {
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  voiceState: VoiceConversationState;
  voiceSupported: boolean;
  onVoiceListen: () => void;
  onVoiceStopListening: () => void;
  onVoiceStopSpeaking: () => void;
}) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  function handleVoice() {
    if (voiceState === "listening") {
      onVoiceStopListening();
      return;
    }
    if (voiceState === "speaking") {
      onVoiceStopSpeaking();
      return;
    }
    onVoiceListen();
  }

  return (
    <form className="conversation-dock" onSubmit={onSend} aria-label="Conversa com DEUS">
      <span className={`dock-processing-dot ${busy ? "is-processing" : ""}`} aria-hidden="true" />
      <textarea
        ref={inputRef}
        value={message}
        onChange={(event) => onMessage(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Fale com DEUS..."
        aria-label="Fale com DEUS"
        rows={1}
        disabled={busy || !authenticated}
      />
      <button
        className={`dock-microphone voice-state-${voiceState}`}
        type="button"
        aria-label={voiceSupported ? `Voz de DEUS: ${voiceState}` : "Entrada por voz ainda indisponivel"}
        title={voiceSupported ? `Voz de DEUS: ${voiceState}` : "Entrada por voz ainda indisponivel"}
        disabled={!authenticated || busy || !voiceSupported || voiceState === "processing"}
        onClick={handleVoice}
      >
        <span aria-hidden="true" />
      </button>
      <button className="dock-send" type="submit" aria-label="Enviar mensagem" disabled={busy || !authenticated || !message.trim()}>
        <span aria-hidden="true">Enviar</span>
      </button>
    </form>
  );
}

function TransientGodResponse({ chat, busy, authError }: Pick<LivingDashboardProps, "chat" | "busy" | "authError">) {
  const latest = [...chat].reverse().find((item) => item.role !== "creator");
  const [dismissedId, setDismissedId] = useState<string | null>(null);

  useEffect(() => {
    if (latest) setDismissedId(null);
  }, [latest?.id]);

  if (authError && dismissedId !== "auth-error") {
    return (
      <section className="transient-response" aria-live="polite">
        <button type="button" onClick={() => setDismissedId("auth-error")} aria-label="Recolher resposta">
          Fechar
        </button>
        <span>DEUS</span>
        <p>{authError}</p>
      </section>
    );
  }

  if (busy) {
    return (
      <section className="transient-response" aria-live="polite">
        <button type="button" onClick={() => setDismissedId("busy")} aria-label="Recolher resposta">
          Fechar
        </button>
        <span>DEUS</span>
        <p>Percebendo.</p>
      </section>
    );
  }

  if (!latest || latest.id === "intro" || latest.id === dismissedId) return null;

  return (
    <section className="transient-response" aria-live="polite">
      <button type="button" onClick={() => setDismissedId(latest.id)} aria-label="Recolher resposta">
        Fechar
      </button>
      <span>{latest.role === "trinity" ? "TRINDADE" : "DEUS"}</span>
      <p>{latest.text}</p>
    </section>
  );
}

function SystemStateBindingLayer({
  pulse,
  loadState,
  authenticated,
}: {
  pulse: Pulse | null;
  loadState: LivingDashboardProps["loadState"];
  authenticated: boolean;
}) {
  const healthy = pulse?.status === "healthy" || pulse?.status === "live";
  const label = !authenticated
    ? "CRIADOR DESCONECTADO"
    : loadState === "error"
      ? "PULSO INDISPONIVEL"
      : healthy
        ? "PULSO ATIVO"
        : "PULSO VERIFICANDO";

  return (
    <section className={`system-state-binding state-${loadState}`} aria-live="polite">
      <span>{label}</span>
      {pulse ? (
        <small>
          {pulse.active_agents} agentes ativos / {pulse.pending_inceptions} inceptions pendentes
        </small>
      ) : null}
    </section>
  );
}

function NotificationLayer({
  notifications,
  onReadNotification,
}: Pick<LivingDashboardProps, "notifications" | "onReadNotification">) {
  const visible = notifications.filter((notification) => notification.status === "unread").slice(0, 3);
  if (visible.length === 0) return null;

  return (
    <section className="real-notification-layer" aria-label="Notificacoes reais do Criador">
      {visible.map((notification) => (
        <article key={notification.id}>
          <button type="button" aria-label={`Dispensar ${notification.title}`} onClick={() => onReadNotification(notification.id)}>
            Fechar
          </button>
          <span>{notification.type}</span>
          <strong>{notification.title}</strong>
          <p>{notification.message}</p>
        </article>
      ))}
    </section>
  );
}

export function LivingDashboard({
  authenticated,
  busy,
  authError,
  message,
  chat,
  pulse,
  loadState,
  notifications,
  activityStates,
  hotspotSummaries,
  demandPanel,
  voiceState,
  voiceSupported,
  voiceError,
  onMessage,
  onSend,
  onVoiceListen,
  onVoiceStopListening,
  onVoiceStopSpeaking,
  onHotspotAction,
  onReadNotification,
}: LivingDashboardProps) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  return (
    <main className="creator-interface-frozen" data-authenticated={authenticated}>
      <FrozenUniverseBackground />
      <UniverseDynamicEffectsLayer activityStates={activityStates} />
      <UniverseInteractionLayer
        hotspotSummaries={hotspotSummaries}
        onHotspotAction={onHotspotAction}
        onFocusConversation={() => inputRef.current?.focus()}
      />
      <SystemStateBindingLayer pulse={pulse} loadState={loadState} authenticated={authenticated} />
      <TransientGodResponse chat={chat} busy={busy} authError={authError ?? voiceError} />
      <NotificationLayer notifications={notifications} onReadNotification={onReadNotification} />
      <ConversationDock
        authenticated={authenticated}
        busy={busy}
        message={message}
        onMessage={onMessage}
        onSend={onSend}
        inputRef={inputRef}
        voiceState={voiceState}
        voiceSupported={voiceSupported}
        onVoiceListen={onVoiceListen}
        onVoiceStopListening={onVoiceStopListening}
        onVoiceStopSpeaking={onVoiceStopSpeaking}
      />
      <section className="on-demand-overlay-host" aria-label="Overlay sob demanda">
        {demandPanel}
      </section>
    </main>
  );
}
