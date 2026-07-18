import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { ChatItem, Pulse } from "../types";

type LivingDashboardProps = {
  authenticated: boolean;
  busy: boolean;
  authError: string | null;
  message: string;
  chat: ChatItem[];
  pulse: Pulse | null;
  demandPanel: ReactNode;
  voiceControls: ReactNode;
  onMessage: (value: string) => void;
  onSend: (event: FormEvent) => void;
};

type NodePoint = {
  id: string;
  label: string;
  group: "core" | "universe" | "agent";
  parentId?: string;
  x: number;
  y: number;
  radius: number;
  hue: number;
  phase: number;
  activity: number;
};

type Edge = {
  from: string;
  to: string;
  strength: number;
  phase: number;
};

type BackgroundPoint = {
  x: number;
  y: number;
  radius: number;
  hue: number;
  phase: number;
  drift: number;
};

const universeSeeds = [
  { id: "engenharia", label: "ENG", hue: 214, x: 0.2, y: 0.53, count: 9 },
  { id: "conhecimento", label: "CON", hue: 286, x: 0.28, y: 0.25, count: 7 },
  { id: "ciencia", label: "CIE", hue: 204, x: 0.49, y: 0.2, count: 8 },
  { id: "negocios", label: "NEG", hue: 37, x: 0.76, y: 0.24, count: 7 },
  { id: "financas", label: "FIN", hue: 148, x: 0.8, y: 0.52, count: 8 },
  { id: "seguranca", label: "SEG", hue: 4, x: 0.72, y: 0.76, count: 6 },
  { id: "criacao", label: "CRI", hue: 46, x: 0.49, y: 0.82, count: 5 },
  { id: "juridico", label: "JUR", hue: 166, x: 0.25, y: 0.76, count: 6 },
] as const;

function buildGraph(width: number, height: number, reducedMotion: boolean) {
  const nodes: NodePoint[] = [];
  const edges: Edge[] = [];
  const background: BackgroundPoint[] = [];
  const centerX = width * 0.51;
  const centerY = height * 0.5;

  nodes.push(
    { id: "deus", label: "DEUS", group: "core", x: centerX, y: centerY, radius: 3.2, hue: 42, phase: 0, activity: 1 },
    {
      id: "sophia",
      label: "SOPHIA",
      group: "core",
      parentId: "deus",
      x: centerX - width * 0.12,
      y: centerY - height * 0.03,
      radius: 7.5,
      hue: 287,
      phase: 1.3,
      activity: 0.9,
    },
    {
      id: "rockmam",
      label: "ROCKMAM",
      group: "core",
      parentId: "deus",
      x: centerX + width * 0.13,
      y: centerY + height * 0.01,
      radius: 7.5,
      hue: 35,
      phase: 3.8,
      activity: 0.9,
    },
  );

  universeSeeds.forEach((seed, universeIndex) => {
    const ux = width * seed.x;
    const uy = height * seed.y;
    nodes.push({
      id: seed.id,
      label: seed.label,
      group: "universe",
      x: ux,
      y: uy,
      radius: 5.4,
      hue: seed.hue,
      phase: universeIndex * 0.73,
      activity: 0.78,
    });
    edges.push({ from: "deus", to: seed.id, strength: 0.34, phase: universeIndex * 0.41 });

    for (let index = 0; index < seed.count; index += 1) {
      const angle = (Math.PI * 2 * index) / seed.count + universeIndex * 0.37;
      const distance = 46 + ((index * 17 + universeIndex * 9) % 72);
      const id = `${seed.id}-agent-${index + 1}`;
      nodes.push({
        id,
        label: "",
        group: "agent",
        parentId: seed.id,
        x: ux + Math.cos(angle) * distance,
        y: uy + Math.sin(angle) * distance,
        radius: 1.45 + (index % 3) * 0.45,
        hue: seed.hue,
        phase: index * 0.65 + universeIndex,
        activity: 0.45 + (index % 4) * 0.11,
      });
      edges.push({ from: seed.id, to: id, strength: 0.64, phase: index * 0.31 + universeIndex });
      if (index > 0) {
        edges.push({ from: `${seed.id}-agent-${index}`, to: id, strength: 0.21, phase: index * 0.52 });
      }
    }
  });

  universeSeeds.forEach((seed, index) => {
    edges.push({ from: seed.id, to: universeSeeds[(index + 1) % universeSeeds.length].id, strength: 0.16, phase: index * 0.7 });
  });

  const backgroundCount = reducedMotion ? 120 : 260;
  const columns = reducedMotion ? 18 : 26;
  const rows = Math.ceil(backgroundCount / columns);
  for (let index = 0; index < backgroundCount; index += 1) {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const jitterX = Math.sin(index * 18.91) * width * 0.025;
    const jitterY = Math.cos(index * 11.37) * height * 0.035;
    const x = width * (0.02 + column / Math.max(1, columns - 1)) + jitterX;
    const y = height * (0.04 + row / Math.max(1, rows)) + jitterY;
    background.push({
      x,
      y,
      radius: 0.55 + ((index * 7) % 8) * 0.16,
      hue: [214, 286, 42, 148, 28, 190][index % 6],
      phase: index * 0.37,
      drift: 0.8 + (index % 5) * 0.18,
    });
  }

  return { nodes, edges, background };
}

function LivingCanvas({ energy }: { energy: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const graphRef = useRef<{ nodes: NodePoint[]; edges: Edge[]; background: BackgroundPoint[] } | null>(null);
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d", { alpha: true });
    if (!canvas || !context) return undefined;

    let width = 0;
    let height = 0;
    let dpr = 1;
    let lastTime = performance.now();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      graphRef.current = buildGraph(width, height, reducedMotion);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const render = (time: number) => {
      if (document.hidden) {
        lastTime = time;
        animationRef.current = requestAnimationFrame(render);
        return;
      }
      const graph = graphRef.current;
      if (!graph) return;

      const dt = Math.min((time - lastTime) / 1000, 0.034);
      lastTime = time;
      const t = time * 0.001;
      const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));

      context.clearRect(0, 0, width, height);
      const glow = context.createRadialGradient(width * 0.52, height * 0.49, 10, width * 0.52, height * 0.49, Math.max(width, height) * 0.78);
      glow.addColorStop(0, "rgba(0, 0, 0, 0.52)");
      glow.addColorStop(0.18, "rgba(30, 18, 8, 0.36)");
      glow.addColorStop(0.34, "rgba(6, 9, 18, 0.22)");
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, width, height);

      graph.background.forEach((point, index) => {
        const pulse = (Math.sin(t * point.drift + point.phase) + 1) * 0.5;
        const px = point.x + Math.sin(t * 0.12 + point.phase) * (reducedMotion ? 2 : 9);
        const py = point.y + Math.cos(t * 0.1 + point.phase) * (reducedMotion ? 2 : 7);
        context.beginPath();
        context.arc(px, py, point.radius + pulse * 0.85, 0, Math.PI * 2);
        context.fillStyle = `hsla(${point.hue}, 100%, 72%, ${0.18 + pulse * 0.42})`;
        context.fill();

        if (index > 0 && index % 2 === 0) {
          const previous = graph.background[index - 1];
          const distance = Math.hypot(previous.x - point.x, previous.y - point.y);
          if (distance < width * 0.18) {
            context.beginPath();
            context.moveTo(previous.x, previous.y);
            context.lineTo(px, py);
            context.strokeStyle = `hsla(${point.hue}, 95%, 64%, ${0.035 + pulse * 0.08})`;
            context.lineWidth = 0.45;
            context.stroke();
          }
        }
      });

      graph.nodes.forEach((node) => {
        if (node.id === "deus") {
          node.x = width * 0.51 + Math.sin(t * 0.24) * 3;
          node.y = height * 0.5 + Math.cos(t * 0.19) * 2;
          return;
        }
        if (node.id === "sophia" || node.id === "rockmam") {
          const side = node.id === "sophia" ? -1 : 1;
          const orbit = width * (node.id === "sophia" ? 0.12 : 0.13);
          const angle = t * (node.id === "sophia" ? 0.18 : -0.15) + node.phase;
          node.x = width * 0.51 + Math.cos(angle) * orbit * side;
          node.y = height * 0.5 + Math.sin(angle) * height * 0.07;
          return;
        }

        const parent = node.parentId ? nodeMap.get(node.parentId) : undefined;
        const seed = universeSeeds.find((item) => item.id === node.id);
        const baseX = node.group === "universe" ? width * (seed?.x ?? 0.5) : (parent?.x ?? width / 2);
        const baseY = node.group === "universe" ? height * (seed?.y ?? 0.5) : (parent?.y ?? height / 2);
        const noiseX = Math.sin(t * (0.21 + node.activity * 0.1) + node.phase) * (node.group === "agent" ? 13 : 7);
        const noiseY = Math.cos(t * (0.17 + node.activity * 0.08) + node.phase * 1.7) * (node.group === "agent" ? 11 : 5);

        if (node.group === "universe") {
          node.x += (baseX + noiseX - node.x) * dt * 0.8;
          node.y += (baseY + noiseY - node.y) * dt * 0.8;
        } else if (node.group === "agent" && parent) {
          const angle = node.phase + t * (0.08 + node.activity * 0.025);
          const distance = 42 + ((node.phase * 27) % 88);
          node.x += (baseX + Math.cos(angle) * distance + noiseX - node.x) * dt * 0.62;
          node.y += (baseY + Math.sin(angle) * distance * 0.72 + noiseY - node.y) * dt * 0.62;
        }
      });

      graph.edges.forEach((edge) => {
        const from = nodeMap.get(edge.from);
        const to = nodeMap.get(edge.to);
        if (!from || !to) return;
        const pulse = (Math.sin(t * 1.9 + edge.phase) + 1) * 0.5;
        const midX = (from.x + to.x) / 2 + Math.sin(t * 0.31 + edge.phase) * 30;
        const midY = (from.y + to.y) / 2 + Math.cos(t * 0.27 + edge.phase) * 20;
        context.beginPath();
        context.moveTo(from.x, from.y);
        context.quadraticCurveTo(midX, midY, to.x, to.y);
        context.strokeStyle = `hsla(${to.hue}, 92%, 68%, ${edge.strength * (0.42 + pulse * 0.32)})`;
        context.lineWidth = edge.from === "deus" ? 1.05 : 0.62;
        context.stroke();
      });

      const center = nodeMap.get("deus");
      if (center) {
        for (let ring = 0; ring < 5; ring += 1) {
          const radiusX = width * (0.09 + ring * 0.026) + Math.sin(t * 0.4 + ring) * 5;
          const radiusY = height * (0.034 + ring * 0.012) + Math.cos(t * 0.33 + ring) * 3;
          context.save();
          context.translate(center.x, center.y);
          context.rotate(-0.28 + t * (0.035 + ring * 0.004));
          context.beginPath();
          context.ellipse(0, 0, radiusX, radiusY, 0, 0, Math.PI * 2);
          context.strokeStyle = `rgba(255, ${184 + ring * 9}, 92, ${0.13 - ring * 0.012})`;
          context.lineWidth = 1.2;
          context.stroke();
          context.restore();
        }

        const voidGradient = context.createRadialGradient(center.x, center.y, 0, center.x, center.y, width * 0.09);
        voidGradient.addColorStop(0, "rgba(0, 0, 0, 0.86)");
        voidGradient.addColorStop(0.45, "rgba(0, 0, 0, 0.64)");
        voidGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
        context.fillStyle = voidGradient;
        context.beginPath();
        context.arc(center.x, center.y, width * 0.09, 0, Math.PI * 2);
        context.fill();
      }

      graph.nodes.forEach((node) => {
        const pulse = (Math.sin(t * (1.2 + node.activity) + node.phase) + 1) * 0.5;
        const alpha = 0.46 + pulse * 0.46;
        const glowRadius = node.radius * (node.group === "agent" ? 5.4 : 8.2) + energy * 5;
        const nodeGlow = context.createRadialGradient(node.x, node.y, 0, node.x, node.y, glowRadius);
        nodeGlow.addColorStop(0, `hsla(${node.hue}, 100%, 88%, ${alpha})`);
        nodeGlow.addColorStop(0.2, `hsla(${node.hue}, 100%, 65%, ${alpha * 0.58})`);
        nodeGlow.addColorStop(1, `hsla(${node.hue}, 100%, 55%, 0)`);
        context.fillStyle = nodeGlow;
        context.beginPath();
        context.arc(node.x, node.y, glowRadius, 0, Math.PI * 2);
        context.fill();
        context.beginPath();
        context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        context.fillStyle = `hsla(${node.hue}, 92%, 78%, 0.78)`;
        context.fill();
        if (node.label) {
          context.font = node.id === "deus" ? "500 7px Inter, sans-serif" : "500 9px Inter, sans-serif";
          context.textAlign = "left";
          context.textBaseline = "middle";
          context.fillStyle = node.id === "deus" ? "rgba(255, 236, 191, 0.32)" : `hsla(${node.hue}, 85%, 84%, 0.7)`;
          context.fillText(node.label, node.x + node.radius + 7, node.y);
        }
      });

      animationRef.current = requestAnimationFrame(render);
    };

    animationRef.current = requestAnimationFrame(render);
    return () => {
      observer.disconnect();
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [energy]);

  return <canvas ref={canvasRef} className="living-canvas" aria-label="Organismo digital vivo do The Creation" />;
}

export function LivingDashboard({
  authenticated,
  busy,
  authError,
  message,
  chat,
  pulse,
  demandPanel,
  voiceControls,
  onMessage,
  onSend,
}: LivingDashboardProps) {
  const clock = useMemo(
    () =>
      new Intl.DateTimeFormat("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    [],
  );
  const [currentTime, setCurrentTime] = useState(clock.format(new Date()));
  const [energy, setEnergy] = useState(0.2);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setCurrentTime(clock.format(new Date()));
      setEnergy((value) => (busy ? Math.min(1, value + 0.08) : 0.14 + Math.random() * 0.24));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [busy, clock]);

  return (
    <main className="living-shell">
      <div className="living-backdrop" />
      <LivingCanvas energy={energy} />

      <header className="living-topbar">
        <div className="living-brand-mark" aria-label="The Creation">
          <span className="living-brand-symbol" />
          <div>
            <strong>THE CREATION</strong>
            <small>CONSCIENCIA VIVA</small>
          </div>
        </div>
        <div className="pulse-indicator" aria-label="Pulso do sistema">
          <span>PULSO</span>
          <i />
          <b>{pulse?.status ?? "ATIVO"}</b>
        </div>
        <div className="cycle-clock">
          <strong>{currentTime}</strong>
          <small>{authenticated ? "CRIADOR CONECTADO" : "ACESSO NECESSARIO"}</small>
        </div>
      </header>

      <section className={`conversation-stream ${chat.length > 1 || authError ? "is-visible" : ""}`}>
        {authError ? (
          <p className="conversation-line role-deus">
            <span>DEUS</span>
            Conexao com o nucleo temporariamente indisponivel.
          </p>
        ) : null}
        {chat.slice(-3).map((item) => (
          <p key={item.id} className={`conversation-line role-${item.role === "creator" ? "creator" : "deus"}`}>
            <span>{item.role === "creator" ? "CRIADOR" : item.role === "trinity" ? "TRINDADE" : "DEUS"}</span>
            {item.text}
          </p>
        ))}
        {busy ? (
          <p className="conversation-line role-deus">
            <span>DEUS</span>
            Estou percebendo...
          </p>
        ) : null}
      </section>

      <form className="creator-input" onSubmit={onSend}>
        <span className={`input-pulse ${busy ? "is-thinking" : ""}`} />
        <input
          value={message}
          onChange={(event) => onMessage(event.target.value)}
          placeholder={busy ? "DEUS esta percebendo..." : "Fale com DEUS..."}
          aria-label="Fale com DEUS"
          disabled={busy || !authenticated}
        />
        <button className="send-button" type="submit" aria-label="Enviar mensagem" disabled={busy || !authenticated || !message.trim()}>
          <span>EN</span>
        </button>
      </form>
      <div className="living-voice-slot">{voiceControls}</div>

      {demandPanel}
    </main>
  );
}
