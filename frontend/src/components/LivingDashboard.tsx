import { FormEvent, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { Agent, ChatItem, ChronicleEntry, CreatorNotification, Pulse, Universe } from "../types";
import type { VoiceConversationState } from "../voice";
import { ChronicleTicker } from "./ChronicleTicker";
import { SystemPulseHeader } from "./SystemPulseHeader";
import { UniverseConstellationLabels } from "./UniverseConstellationLabels";

export type EntityActivityState = "idle" | "active" | "processing" | "waiting" | "completed" | "warning" | "error" | "offline";

function voiceStateLabel(state: VoiceConversationState) {
  if (state === "listening") return "Ouvindo";
  if (state === "processing") return "Processando";
  if (state === "responding") return "Respondendo";
  if (state === "speaking") return "Reproduzindo";
  if (state === "error") return "Erro";
  return "Pronto";
}

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
  agents: Agent[];
  universes: Universe[];
  chronicles: ChronicleEntry[];
  activityStates: Record<string, EntityActivityState>;
  hotspotSummaries: Record<string, HotspotSummary>;
  demandPanel: ReactNode;
  onSelectPanel: (panel: "universes" | "chronicle") => void;
  voiceState: VoiceConversationState;
  voiceSupported: boolean;
  voiceError: string | null;
  authBusy: boolean;
  username: string;
  password: string;
  onUsername: (value: string) => void;
  onPassword: (value: string) => void;
  onLogin: (event: FormEvent) => void;
  onMessage: (value: string) => void;
  onSend: (event: FormEvent) => void;
  onVoiceListen: () => void;
  onVoiceStopListening: () => void;
  onVoiceStopSpeaking: () => void;
  onReadNotification: (notificationId: string) => void;
};

type VisualTone = "gold" | "violet" | "blue" | "green" | "red";

type Hotspot = {
  id: string;
  label: string;
  type: "core";
  xPercent: number;
  yPercent: number;
  radiusPercent: number;
  hue: number;
  tone: VisualTone;
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
  { id: "deus", label: "DEUS", type: "core", xPercent: 50, yPercent: 45, radiusPercent: 5.2, hue: 42, tone: "gold" },
  { id: "sophia", label: "SOPHIA", type: "core", xPercent: 39, yPercent: 43, radiusPercent: 3.4, hue: 287, tone: "violet" },
  { id: "rockmam", label: "ROCKMAM", type: "core", xPercent: 61, yPercent: 47, radiusPercent: 3.4, hue: 35, tone: "gold" },
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

function stableUnit(value: string, salt = 0) {
  let hash = 2166136261 + salt;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function LivingUniverseScene({
  activityStates,
  agents,
  universes,
}: {
  activityStates: Record<string, EntityActivityState>;
  agents: Agent[];
  universes: Universe[];
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationRef = useRef<number | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const pointerRef = useRef({ x: 0, y: 0 });
  const activityRef = useRef(activityStates);
  const agentsRef = useRef(agents);
  const universesRef = useRef(universes);

  useEffect(() => {
    activityRef.current = activityStates;
  }, [activityStates]);

  useEffect(() => {
    agentsRef.current = agents;
  }, [agents]);

  useEffect(() => {
    universesRef.current = universes;
  }, [universes]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d", { alpha: false });
    if (!canvas || !context) return undefined;
    const cnv = canvas;
    const ctx = context;

    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reducedMotion = reducedMotionQuery.matches;
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

    function drawNeuralPath(
      start: { x: number; y: number },
      end: { x: number; y: number },
      hue: number,
      phase: number,
      alpha: number,
      time: number,
    ) {
      const bend = Math.sin(phase * 2.7) * Math.min(width, height) * 0.035;
      const control = {
        x: (start.x + end.x) / 2 + bend,
        y: (start.y + end.y) / 2 - bend * 0.6,
      };
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.quadraticCurveTo(control.x, control.y, end.x, end.y);
      ctx.strokeStyle = `hsla(${hue}, 92%, 72%, ${alpha})`;
      ctx.lineWidth = 0.45;
      ctx.stroke();

      const progress = reducedMotion ? 0.5 : (time * (0.07 + (phase % 5) * 0.009) + phase) % 1;
      const inverse = 1 - progress;
      const signalX = inverse * inverse * start.x + 2 * inverse * progress * control.x + progress * progress * end.x;
      const signalY = inverse * inverse * start.y + 2 * inverse * progress * control.y + progress * progress * end.y;
      drawGlow(signalX, signalY, Math.max(7, width * 0.007), hue, alpha * 1.8);
      ctx.beginPath();
      ctx.arc(signalX, signalY, 0.8, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${hue}, 100%, 88%, ${Math.min(0.72, alpha * 3)})`;
      ctx.fill();
    }

    // Deterministic star-cluster network around an entity point (SOPHIA/ROCKMAM/each
    // active Universe), matching the reference image's constellation motif — every
    // point/edge is a pure function of (seed, index) via stableUnit, not random per frame.
    function drawConstellationCluster(cx: number, cy: number, hue: number, seed: string, radius: number, time: number) {
      const count = 7;
      const points = Array.from({ length: count }, (_, index) => {
        const angle = stableUnit(seed, index * 7 + 1) * Math.PI * 2;
        const dist = (0.35 + stableUnit(seed, index * 13 + 3) * 0.65) * radius;
        return {
          x: cx + Math.cos(angle) * dist,
          y: cy + Math.sin(angle) * dist * 0.68,
          phase: stableUnit(seed, index * 19 + 5) * Math.PI * 2,
          speed: 0.6 + stableUnit(seed, index * 23 + 7) * 0.8,
        };
      });

      ctx.strokeStyle = `hsla(${hue}, 85%, 75%, 0.15)`;
      ctx.lineWidth = 0.5;
      for (let index = 0; index < points.length; index += 1) {
        const a = points[index];
        const b = points[(index + 1) % points.length];
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      for (let index = 0; index < 3; index += 1) {
        const from = Math.floor(stableUnit(seed, index * 31 + 11) * points.length);
        const to = Math.floor(stableUnit(seed, index * 37 + 17) * points.length);
        if (from === to) continue;
        ctx.beginPath();
        ctx.moveTo(points[from].x, points[from].y);
        ctx.lineTo(points[to].x, points[to].y);
        ctx.stroke();
      }
      for (let index = 0; index < Math.min(3, points.length); index += 1) {
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(points[index].x, points[index].y);
        ctx.stroke();
      }

      for (const star of points) {
        const twinkle = reducedMotion ? 0.5 : (Math.sin(time * star.speed + star.phase) + 1) * 0.5;
        ctx.beginPath();
        ctx.arc(star.x, star.y, 0.9 + twinkle * 0.6, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${hue}, 100%, 85%, ${0.32 + twinkle * 0.42})`;
        ctx.fill();
      }
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

      const corePoints = new Map(hotspots.map((hotspot) => [hotspot.id, point(hotspot, t)]));
      const deus = corePoints.get("deus")!;
      const sophia = corePoints.get("sophia")!;
      const rockmam = corePoints.get("rockmam")!;

      drawNeuralPath(deus, sophia, 287, 0.12, 0.18, t);
      drawNeuralPath(deus, rockmam, 38, 0.62, 0.18, t);

      const activeUniverses = universesRef.current.filter((universe) => universe.active);
      const universePoints = activeUniverses.map((universe, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, activeUniverses.length) - Math.PI / 2;
        const breathing = reducedMotion ? 0 : Math.sin(t * 0.08 + index * 1.7) * 0.012;
        return {
          id: universe.id,
          x: width * (0.5 + Math.cos(angle) * (0.31 + breathing)),
          y: height * (0.45 + Math.sin(angle) * (0.31 + breathing) * 0.72),
          hue: [210, 278, 158, 34, 192, 326][index % 6],
        };
      });

      for (let index = 0; index < universePoints.length; index += 1) {
        const region = universePoints[index];
        const regionPulse = (Math.sin(t * 0.42 + index * 1.9) + 1) * 0.5;
        drawGlow(region.x, region.y, width * 0.105, region.hue, 0.025 + regionPulse * 0.018);
        drawConstellationCluster(region.x, region.y, region.hue, region.id, width * 0.062, t);
        ctx.beginPath();
        ctx.arc(region.x, region.y, 0.8 + regionPulse * 0.6, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${region.hue}, 90%, 78%, ${0.12 + regionPulse * 0.1})`;
        ctx.fill();
        drawNeuralPath(region, deus, region.hue, index * 0.17, 0.035, t);
      }

      const visibleAgents = agentsRef.current.filter((agent) => agent.enabled).slice(0, 96);
      visibleAgents.forEach((agent, index) => {
        if (universePoints.length === 0) return;
        const region = universePoints[Math.floor(stableUnit(agent.universe || agent.id, 7) * universePoints.length) % universePoints.length];
        const angle = stableUnit(agent.id, 11) * Math.PI * 2;
        const distance = width * (0.025 + stableUnit(agent.id, 23) * 0.075);
        const drift = reducedMotion ? 0 : Math.sin(t * (0.11 + stableUnit(agent.id, 31) * 0.08) + index) * width * 0.006;
        const node = {
          x: region.x + Math.cos(angle) * distance + drift,
          y: region.y + Math.sin(angle) * distance * 0.58 + drift * 0.35,
        };
        const operational = !["idle", "offline", "disabled"].includes(agent.status.toLowerCase());
        const nodePulse = (Math.sin(t * (operational ? 1.8 : 0.72) + index * 1.37) + 1) * 0.5;
        drawNeuralPath(node, region, region.hue, stableUnit(agent.id, 43), operational ? 0.09 : 0.035, t);
        drawGlow(node.x, node.y, width * 0.012, region.hue, operational ? 0.13 + nodePulse * 0.08 : 0.055 + nodePulse * 0.035);
        ctx.beginPath();
        ctx.arc(node.x, node.y, 0.75 + nodePulse * 0.7, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${region.hue}, 100%, 86%, ${operational ? 0.68 : 0.34})`;
        ctx.fill();
      });

      for (const hotspot of hotspots) {
        const p = point(hotspot, t);
        const state = activity[hotspot.id] ?? "idle";
        const active = state !== "idle";
        const pulse = (Math.sin(t * (active ? 2.6 : 1.1) + hotspot.hue) + 1) * 0.5;
        const isDeus = hotspot.id === "deus";
        // DEUS reads as the dominant sacred-geometry sun (per reference image); SOPHIA/ROCKMAM stay
        // small orbiting points since their identity already has a persistent DOM card off to the side.
        const baseRadius = width * (isDeus ? 0.026 : 0.0038);
        drawGlow(p.x, p.y, width * (isDeus ? 0.13 : 0.05), hotspot.hue, active ? (isDeus ? 0.34 : 0.14) + pulse * 0.05 : (isDeus ? 0.24 : 0.065) + pulse * 0.035);

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(t * (hotspot.id === "rockmam" ? -0.08 : 0.08));
        if (isDeus) {
          for (let ring = 0; ring < 4; ring += 1) {
            ctx.beginPath();
            ctx.arc(0, 0, baseRadius * (0.55 + ring * 0.42), 0, Math.PI * 2);
            ctx.strokeStyle = `hsla(${hotspot.hue}, 92%, 82%, ${0.34 - ring * 0.055 + pulse * 0.03})`;
            ctx.lineWidth = 0.9;
            ctx.stroke();
          }
          for (let index = 0; index < 6; index += 1) {
            const angle = (Math.PI * 2 * index) / 6;
            ctx.beginPath();
            ctx.arc(Math.cos(angle) * baseRadius * 0.55, Math.sin(angle) * baseRadius * 0.55, baseRadius * 0.55, 0, Math.PI * 2);
            ctx.strokeStyle = `hsla(${hotspot.hue}, 92%, 82%, 0.22)`;
            ctx.lineWidth = 0.7;
            ctx.stroke();
          }
        } else {
          const rings = 2;
          for (let ring = 0; ring < rings; ring += 1) {
            ctx.beginPath();
            ctx.ellipse(0, 0, baseRadius * (3.2 + ring * 1.7), baseRadius * (0.75 + ring * 0.35), ring * 0.42, 0, Math.PI * 2);
            ctx.strokeStyle = `hsla(${hotspot.hue}, 90%, 78%, ${0.12 - ring * 0.03 + pulse * 0.025})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
        ctx.restore();

        if (!isDeus) {
          drawConstellationCluster(p.x, p.y, hotspot.hue, hotspot.id, width * 0.05, t);
          for (let index = 0; index < 3; index += 1) {
            const angle = t * (hotspot.id === "rockmam" ? -0.12 : 0.12) + (Math.PI * 2 * index) / 3;
            const orbitRadius = baseRadius * (3.4 + (index % 2) * 0.8);
            const satellite = { x: p.x + Math.cos(angle) * orbitRadius * 1.8, y: p.y + Math.sin(angle) * orbitRadius * 0.58 };
            drawGlow(satellite.x, satellite.y, baseRadius * 1.6, hotspot.hue, 0.07 + pulse * 0.04);
            ctx.beginPath();
            ctx.arc(satellite.x, satellite.y, 0.55, 0, Math.PI * 2);
            ctx.fillStyle = `hsla(${hotspot.hue}, 100%, 86%, ${0.45 + pulse * 0.18})`;
            ctx.fill();
          }
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, baseRadius * (isDeus ? 0.62 : 0.28), 0, Math.PI * 2);
        if (isDeus) {
          const core = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, baseRadius * 0.62);
          core.addColorStop(0, "rgba(255, 250, 235, 0.95)");
          core.addColorStop(0.5, `hsla(${hotspot.hue}, 100%, 72%, ${0.75 + pulse * 0.1})`);
          core.addColorStop(1, `hsla(${hotspot.hue}, 100%, 55%, 0.35)`);
          ctx.fillStyle = core;
        } else {
          ctx.fillStyle = `hsla(${hotspot.hue}, 92%, 76%, 0.64)`;
        }
        ctx.fill();

        if (!isDeus) {
          ctx.font = "500 7px Inter, sans-serif";
          ctx.textBaseline = "middle";
          ctx.fillStyle = `hsla(${hotspot.hue}, 86%, 82%, 0.42)`;
          ctx.fillText(hotspot.label, p.x + baseRadius * 1.55, p.y - baseRadius * 0.12);
        }
      }

      animationRef.current = requestAnimationFrame(draw);
    }

    function handlePointerMove(event: PointerEvent) {
      pointerRef.current = {
        x: (event.clientX / Math.max(1, width) - 0.5) * 2,
        y: (event.clientY / Math.max(1, height) - 0.5) * 2,
      };
    }

    function handleReducedMotionChange(event: MediaQueryListEvent) {
      reducedMotion = event.matches;
      particlesRef.current = createParticles(reducedMotion ? 160 : 340);
    }

    const observer = new ResizeObserver(resize);
    observer.observe(cnv);
    window.addEventListener("pointermove", handlePointerMove);
    reducedMotionQuery.addEventListener("change", handleReducedMotionChange);
    resize();
    animationRef.current = requestAnimationFrame(draw);

    return () => {
      observer.disconnect();
      window.removeEventListener("pointermove", handlePointerMove);
      reducedMotionQuery.removeEventListener("change", handleReducedMotionChange);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  return <canvas ref={canvasRef} className="living-universe-canvas" aria-label="Universo vivo funcional do The Creation" />;
}

const deusHotspot = hotspots.find((hotspot) => hotspot.id === "deus")!;

function DeusCoreLabel() {
  return (
    <div
      className="deus-core-label"
      style={{ "--label-x": `${deusHotspot.xPercent}%`, "--label-y": `${deusHotspot.yPercent}%` } as CSSProperties}
      aria-hidden="true"
    >
      <strong>DEUS</strong>
      <span>CONSCIÊNCIA SUPREMA</span>
      <span>FONTE E AUTORIDADE</span>
    </div>
  );
}

function UniverseInteractionLayer({
  hotspotSummaries,
  onFocusConversation,
}: {
  hotspotSummaries: Record<string, HotspotSummary>;
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
        aria-label={voiceSupported ? `Voz de DEUS: ${voiceStateLabel(voiceState)}` : "Entrada por voz ainda indisponivel"}
        title={voiceSupported ? `Voz de DEUS: ${voiceStateLabel(voiceState)}` : "Entrada por voz ainda indisponivel"}
        disabled={!authenticated || busy || !voiceSupported || voiceState === "processing" || voiceState === "responding"}
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

function CreatorAccess({
  username,
  password,
  authBusy,
  authError,
  onUsername,
  onPassword,
  onLogin,
}: Pick<
  LivingDashboardProps,
  "username" | "password" | "authBusy" | "authError" | "onUsername" | "onPassword" | "onLogin"
>) {
  return (
    <form className="creator-access" onSubmit={onLogin} aria-label="Acesso do Criador">
      <span>DEUS</span>
      <input
        value={username}
        onChange={(event) => onUsername(event.target.value)}
        aria-label="Identidade do Criador"
        placeholder="Criador"
        autoComplete="username"
        disabled={authBusy}
      />
      <input
        type="password"
        value={password}
        onChange={(event) => onPassword(event.target.value)}
        aria-label="Senha do Criador"
        placeholder="Presença reservada"
        autoComplete="current-password"
        disabled={authBusy}
      />
      <button type="submit" disabled={authBusy || !username.trim() || !password}>
        {authBusy ? "Conectando" : "Entrar"}
      </button>
      {authError ? <p>{authError}</p> : <small>Canal direto do Criador</small>}
    </form>
  );
}

function TransientGodResponse({
  chat,
  busy,
  alertMessage,
}: Pick<LivingDashboardProps, "chat" | "busy"> & { alertMessage: string | null }) {
  const latest = [...chat].reverse().find((item) => item.role !== "creator");
  const [dismissedId, setDismissedId] = useState<string | null>(null);
  const [trackedLatestId, setTrackedLatestId] = useState(latest?.id);

  if (latest?.id !== trackedLatestId) {
    setTrackedLatestId(latest?.id);
    setDismissedId(null);
  }

  if (alertMessage && dismissedId !== "voice-error") {
    return (
      <section className="transient-response" aria-live="polite">
        <button type="button" onClick={() => setDismissedId("voice-error")} aria-label="Recolher resposta">
          Fechar
        </button>
        <span>DEUS</span>
        <p>{alertMessage}</p>
      </section>
    );
  }

  if (busy && dismissedId !== "busy") {
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
  authBusy,
  authError,
  username,
  password,
  message,
  chat,
  pulse,
  loadState,
  notifications,
  agents,
  universes,
  chronicles,
  activityStates,
  hotspotSummaries,
  demandPanel,
  onSelectPanel,
  voiceState,
  voiceSupported,
  voiceError,
  onUsername,
  onPassword,
  onLogin,
  onMessage,
  onSend,
  onVoiceListen,
  onVoiceStopListening,
  onVoiceStopSpeaking,
  onReadNotification,
}: LivingDashboardProps) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  return (
    <main className="creator-interface-living" data-authenticated={authenticated}>
      <LivingUniverseScene activityStates={activityStates} agents={agents} universes={universes} />
      <DeusCoreLabel />
      <UniverseInteractionLayer
        hotspotSummaries={hotspotSummaries}
        onFocusConversation={() => inputRef.current?.focus()}
      />
      <SystemPulseHeader pulse={pulse} authenticated={authenticated} />
      <UniverseConstellationLabels agents={agents} universes={universes} onSelectPanel={onSelectPanel} />
      <SystemStateBindingLayer pulse={pulse} loadState={loadState} authenticated={authenticated} />
      <TransientGodResponse chat={chat} busy={busy} alertMessage={authenticated ? voiceError : null} />
      <NotificationLayer notifications={notifications} onReadNotification={onReadNotification} />
      <ChronicleTicker entries={chronicles} onOpenFull={() => onSelectPanel("chronicle")} />
      {authenticated ? (
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
      ) : (
        <CreatorAccess
          username={username}
          password={password}
          authBusy={authBusy}
          authError={authError}
          onUsername={onUsername}
          onPassword={onPassword}
          onLogin={onLogin}
        />
      )}
      <section className="on-demand-overlay-host" aria-label="Overlay sob demanda">
        {demandPanel}
      </section>
    </main>
  );
}
