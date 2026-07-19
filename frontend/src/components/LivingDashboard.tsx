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

type VisualTone = "gold" | "violet" | "blue" | "green" | "red";

type Hotspot = {
  id: string;
  label: string;
  type: "core" | "universe";
  xPercent: number;
  yPercent: number;
  radiusPercent: number;
  hue: number;
  tone: VisualTone;
  agents: number;
};

type Particle = {
  x: number;
  y: number;
  depth: number;
  hue: number;
  phase: number;
  speed: number;
  radius: number;
};

const hotspots: Hotspot[] = [
  { id: "deus", label: "DEUS", type: "core", xPercent: 50.2, yPercent: 50.9, radiusPercent: 5.6, hue: 42, tone: "gold", agents: 0 },
  { id: "sophia", label: "SOPHIA", type: "core", xPercent: 39.6, yPercent: 48.5, radiusPercent: 4.5, hue: 287, tone: "violet", agents: 0 },
  { id: "rockmam", label: "ROCKMAM", type: "core", xPercent: 62.8, yPercent: 51.5, radiusPercent: 4.3, hue: 35, tone: "gold", agents: 0 },
  { id: "eng", label: "ENGENHARIA", type: "universe", xPercent: 21.4, yPercent: 51.8, radiusPercent: 4.2, hue: 214, tone: "blue", agents: 9 },
  { id: "jur", label: "JURIDICO", type: "universe", xPercent: 27.4, yPercent: 78.8, radiusPercent: 4.0, hue: 166, tone: "green", agents: 6 },
  { id: "fin", label: "FINANCAS", type: "universe", xPercent: 79.5, yPercent: 47.7, radiusPercent: 4.1, hue: 148, tone: "green", agents: 8 },
  { id: "seg", label: "SEGURANCA", type: "universe", xPercent: 69.2, yPercent: 75.4, radiusPercent: 3.8, hue: 4, tone: "red", agents: 6 },
  { id: "neg", label: "NEGOCIOS", type: "universe", xPercent: 76.6, yPercent: 19.6, radiusPercent: 4.0, hue: 37, tone: "gold", agents: 7 },
  { id: "cie", label: "CIENCIA", type: "universe", xPercent: 48.8, yPercent: 16.8, radiusPercent: 3.9, hue: 204, tone: "blue", agents: 8 },
  { id: "con", label: "CONHECIMENTO", type: "universe", xPercent: 24.2, yPercent: 27.0, radiusPercent: 4.0, hue: 286, tone: "violet", agents: 7 },
  { id: "cri", label: "CRIACAO", type: "universe", xPercent: 48.3, yPercent: 83.5, radiusPercent: 3.7, hue: 46, tone: "gold", agents: 5 },
];

function createParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, index) => ({
    x: (Math.sin(index * 39.17) + 1) / 2,
    y: (Math.cos(index * 27.31) + 1) / 2,
    depth: 0.25 + ((index * 17) % 100) / 100,
    hue: [214, 286, 42, 148, 28, 190][index % 6],
    phase: index * 0.41,
    speed: 0.08 + (index % 9) * 0.012,
    radius: 0.45 + (index % 5) * 0.16,
  }));
}

function LivingUniverseScene({ activityStates }: { activityStates: Record<string, EntityActivityState> }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationRef = useRef<number | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const pointerRef = useRef({ x: 0, y: 0 });
  const activityRef = useRef(activityStates);

  useEffect(() => {
    activityRef.current = activityStates;
  }, [activityStates]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d", { alpha: false });
    if (!canvas || !context) return undefined;
    const cnv = canvas;
    const ctx = context;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    particlesRef.current = createParticles(reducedMotion ? 160 : 340);
    let width = 0;
    let height = 0;
    let dpr = 1;
    let lastTime = performance.now();

    function resize() {
      const rect = cnv.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      cnv.width = Math.floor(width * dpr);
      cnv.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function point(hotspot: Hotspot, time: number) {
      const parallaxX = pointerRef.current.x * (hotspot.type === "core" ? 9 : 18);
      const parallaxY = pointerRef.current.y * (hotspot.type === "core" ? 6 : 13);
      const orbit = hotspot.id === "sophia" || hotspot.id === "rockmam";
      const side = hotspot.id === "sophia" ? -1 : hotspot.id === "rockmam" ? 1 : 0;
      const orbitX = orbit && !reducedMotion ? Math.cos(time * 0.16 + side) * width * 0.018 : 0;
      const orbitY = orbit && !reducedMotion ? Math.sin(time * 0.13 + side) * height * 0.035 : 0;
      return {
        x: (hotspot.xPercent / 100) * width + parallaxX + orbitX,
        y: (hotspot.yPercent / 100) * height + parallaxY + orbitY,
      };
    }

    function drawGlow(x: number, y: number, radius: number, hue: number, alpha: number) {
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
      gradient.addColorStop(0, `hsla(${hue}, 100%, 88%, ${alpha})`);
      gradient.addColorStop(0.2, `hsla(${hue}, 100%, 60%, ${alpha * 0.45})`);
      gradient.addColorStop(1, `hsla(${hue}, 100%, 40%, 0)`);
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
    }

    function draw(timeMs: number) {
      if (document.hidden) {
        lastTime = timeMs;
        animationRef.current = requestAnimationFrame(draw);
        return;
      }
      const dt = Math.min((timeMs - lastTime) / 1000, 0.033);
      lastTime = timeMs;
      const t = timeMs * 0.001;
      const activity = activityRef.current;

      ctx.fillStyle = "#000103";
      ctx.fillRect(0, 0, width, height);

      const coreGradient = ctx.createRadialGradient(width * 0.5, height * 0.51, 0, width * 0.5, height * 0.51, width * 0.72);
      coreGradient.addColorStop(0, "rgba(18, 12, 5, 0.92)");
      coreGradient.addColorStop(0.23, "rgba(7, 12, 24, 0.82)");
      coreGradient.addColorStop(0.58, "rgba(0, 2, 8, 0.96)");
      coreGradient.addColorStop(1, "rgba(0, 0, 0, 1)");
      ctx.fillStyle = coreGradient;
      ctx.fillRect(0, 0, width, height);

      for (const particle of particlesRef.current) {
        if (!reducedMotion) {
          particle.x += Math.sin(t * particle.speed + particle.phase) * dt * 0.0016 * particle.depth;
          particle.y += Math.cos(t * particle.speed * 0.8 + particle.phase) * dt * 0.0012 * particle.depth;
        }
        const px = ((particle.x % 1) + pointerRef.current.x * 0.014 * particle.depth) * width;
        const py = ((particle.y % 1) + pointerRef.current.y * 0.011 * particle.depth) * height;
        const pulse = (Math.sin(t * (0.8 + particle.depth) + particle.phase) + 1) * 0.5;
        ctx.beginPath();
        ctx.arc(px, py, particle.radius + pulse * 0.8, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${particle.hue}, 100%, ${58 + particle.depth * 30}%, ${0.08 + pulse * 0.42})`;
        ctx.fill();
      }

      const center = point(hotspots[0], t);
      for (const hotspot of hotspots.slice(1)) {
        const target = point(hotspot, t);
        const state = activity[hotspot.id] ?? "idle";
        const pulse = (Math.sin(t * 1.4 + hotspot.hue) + 1) * 0.5;
        ctx.beginPath();
        ctx.moveTo(center.x, center.y);
        ctx.bezierCurveTo(
          (center.x + target.x) / 2,
          center.y + Math.sin(t + hotspot.hue) * height * 0.08,
          (center.x + target.x) / 2,
          target.y + Math.cos(t + hotspot.hue) * height * 0.08,
          target.x,
          target.y,
        );
        ctx.strokeStyle = `hsla(${hotspot.hue}, 95%, 70%, ${state === "idle" ? 0.11 : 0.24 + pulse * 0.16})`;
        ctx.lineWidth = hotspot.type === "core" ? 1.2 : 0.7;
        ctx.stroke();
      }

      for (const hotspot of hotspots) {
        const p = point(hotspot, t);
        const state = activity[hotspot.id] ?? "idle";
        const active = state !== "idle";
        const pulse = (Math.sin(t * (active ? 2.6 : 1.1) + hotspot.hue) + 1) * 0.5;
        const baseRadius = width * hotspot.radiusPercent * 0.0048;
        const glowRadius = baseRadius * (hotspot.type === "core" ? 13 : 10) * (active ? 1.22 : 1);
        drawGlow(p.x, p.y, glowRadius, hotspot.hue, active ? 0.46 + pulse * 0.18 : 0.25 + pulse * 0.08);

        if (hotspot.type === "core") {
          ctx.save();
          ctx.translate(p.x, p.y);
          ctx.rotate(t * (hotspot.id === "rockmam" ? -0.1 : 0.11));
          for (let ring = 0; ring < (hotspot.id === "deus" ? 5 : 3); ring += 1) {
            ctx.beginPath();
            ctx.ellipse(0, 0, baseRadius * (7 + ring * 2.5), baseRadius * (2.4 + ring * 0.8), ring * 0.36, 0, Math.PI * 2);
            ctx.strokeStyle = `hsla(${hotspot.hue}, 90%, 72%, ${0.13 - ring * 0.018 + pulse * 0.03})`;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
          ctx.restore();
        } else {
          const count = Math.max(4, hotspot.agents);
          for (let index = 0; index < count; index += 1) {
            const angle = (Math.PI * 2 * index) / count + t * (reducedMotion ? 0 : 0.05) + hotspot.hue;
            const distance = baseRadius * (5 + (index % 4));
            const ax = p.x + Math.cos(angle) * distance;
            const ay = p.y + Math.sin(angle) * distance * 0.72;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(ax, ay);
            ctx.strokeStyle = `hsla(${hotspot.hue}, 90%, 66%, ${0.12 + pulse * 0.08})`;
            ctx.lineWidth = 0.45;
            ctx.stroke();
            drawGlow(ax, ay, baseRadius * 1.6, hotspot.hue, 0.25 + pulse * 0.12);
          }
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, baseRadius * (hotspot.id === "deus" ? 0.7 : 1.1), 0, Math.PI * 2);
        ctx.fillStyle = hotspot.id === "deus" ? "rgba(255, 235, 190, 0.36)" : `hsla(${hotspot.hue}, 92%, 76%, 0.82)`;
        ctx.fill();
        ctx.font = hotspot.id === "deus" ? "500 7px Inter, sans-serif" : "500 10px Inter, sans-serif";
        ctx.textBaseline = "middle";
        ctx.fillStyle = hotspot.id === "deus" ? "rgba(255, 230, 185, 0.36)" : `hsla(${hotspot.hue}, 86%, 82%, 0.75)`;
        ctx.fillText(hotspot.label, p.x + baseRadius * 1.8, p.y);
      }

      animationRef.current = requestAnimationFrame(draw);
    }

    function handlePointerMove(event: PointerEvent) {
      pointerRef.current = {
        x: (event.clientX / Math.max(1, width) - 0.5) * 2,
        y: (event.clientY / Math.max(1, height) - 0.5) * 2,
      };
    }

    const observer = new ResizeObserver(resize);
    observer.observe(cnv);
    window.addEventListener("pointermove", handlePointerMove);
    resize();
    animationRef.current = requestAnimationFrame(draw);

    return () => {
      observer.disconnect();
      window.removeEventListener("pointermove", handlePointerMove);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  return <canvas ref={canvasRef} className="living-universe-canvas" aria-label="Universo vivo funcional do The Creation" />;
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
      {hotspots.map((hotspot) => (
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
    <main className="creator-interface-living" data-authenticated={authenticated}>
      <LivingUniverseScene activityStates={activityStates} />
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
