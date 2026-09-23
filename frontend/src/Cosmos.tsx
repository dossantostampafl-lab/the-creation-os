import { useEffect, useRef } from "react";
import { voiceActivity } from "./voice";

export type CosmosMood = "idle" | "listening" | "thinking" | "speaking";

type CosmosUniverse = { id: string; name: string; active: boolean };

type Props = {
  universes: CosmosUniverse[];
  signal: number;
  mood: CosmosMood;
};

type Vec = [number, number, number];
type Pulse = { edge: number; t: number; speed: number; forward: boolean; warm: boolean };
type Comet = { x: number; y: number; vx: number; vy: number; life: number };

const NEURON_COUNT = 1400;
const CAMERA = 3.4;

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randomDirection(rng: () => number): Vec {
  const u = rng() * 2 - 1;
  const theta = rng() * Math.PI * 2;
  const s = Math.sqrt(1 - u * u);
  return [s * Math.cos(theta), u, s * Math.sin(theta)];
}

/** Samples a point on a stylised brain: two folded hemispheres, cerebellum and brainstem. */
function brainPoint(rng: () => number): Vec {
  const region = rng();
  if (region < 0.84) {
    const side = rng() < 0.5 ? -1 : 1;
    const [dx, dy, dz] = randomDirection(rng);
    const shell = 1 - rng() ** 3 * 0.4;
    const gyri = 1 + 0.075 * Math.sin(dz * 13 + dy * 8) * Math.sin(dy * 11 - dx * 6);
    let x = side * 0.47 + dx * 0.55 * shell * gyri;
    let y = dy * 0.72 * shell * gyri + 0.12;
    const z = dz * 1.12 * shell * gyri;
    if (Math.abs(x) < 0.05) x = side * (0.05 + rng() * 0.03);
    if (y < -0.3) y = -0.3 + (y + 0.3) * 0.4;
    return [x, y, z];
  }
  if (region < 0.95) {
    const [dx, dy, dz] = randomDirection(rng);
    const shell = 1 - rng() ** 3 * 0.4;
    const folds = 1 + 0.06 * Math.sin(dy * 30);
    return [dx * 0.6 * shell, -0.5 + dy * 0.24 * shell * folds, -0.78 + dz * 0.34 * shell];
  }
  const angle = rng() * Math.PI * 2;
  const depth = rng();
  return [Math.cos(angle) * 0.11, -0.42 - depth * 0.7, -0.38 - depth * 0.12 + Math.sin(angle) * 0.11];
}

function buildBrain() {
  const rng = mulberry32(20260922);
  const points: Vec[] = Array.from({ length: NEURON_COUNT }, () => brainPoint(rng));
  const edges: Array<[number, number]> = [];
  const seen = new Set<string>();
  for (let i = 0; i < points.length; i += 1) {
    const nearest: Array<[number, number]> = [];
    for (let j = 0; j < points.length; j += 1) {
      if (i === j) continue;
      const dx = points[i][0] - points[j][0];
      const dy = points[i][1] - points[j][1];
      const dz = points[i][2] - points[j][2];
      const d = dx * dx + dy * dy + dz * dz;
      if (d > 0.06) continue;
      nearest.push([d, j]);
    }
    nearest.sort((a, b) => a[0] - b[0]);
    for (const [, j] of nearest.slice(0, 3)) {
      const key = i < j ? `${i}:${j}` : `${j}:${i}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push([i, j]);
    }
  }
  return { points, edges };
}

function glowSprite(color: string, size: number) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "#ffffff");
  g.addColorStop(0.18, color);
  g.addColorStop(1, "transparent");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return canvas;
}

function galaxySprite(hue: number, seed: number) {
  const size = 96;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const rng = mulberry32(seed);
  const core = ctx.createRadialGradient(48, 48, 0, 48, 48, 26);
  core.addColorStop(0, `hsla(${hue}, 100%, 92%, 0.95)`);
  core.addColorStop(0.35, `hsla(${hue}, 90%, 65%, 0.35)`);
  core.addColorStop(1, "transparent");
  ctx.fillStyle = core;
  ctx.fillRect(0, 0, size, size);
  for (let i = 0; i < 420; i += 1) {
    const arm = i % 2;
    const r = rng() ** 0.7 * 44;
    const a = r * 0.16 + arm * Math.PI + (rng() - 0.5) * 0.7;
    ctx.fillStyle = `hsla(${hue + (rng() - 0.5) * 40}, 90%, ${60 + rng() * 35}%, ${0.25 + rng() * 0.6})`;
    ctx.fillRect(48 + Math.cos(a) * r, 48 + Math.sin(a) * r * 0.9, 1.1, 1.1);
  }
  return canvas;
}

function nebulaLayer(width: number, height: number) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  const rng = mulberry32(7);
  const clouds = ["#4b1f7a", "#132f7a", "#0c5566", "#6a1d5c", "#1c1a5e"];
  for (let i = 0; i < 16; i += 1) {
    const x = rng() * width;
    const y = rng() * height;
    const r = (0.2 + rng() * 0.45) * Math.max(width, height);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `${clouds[i % clouds.length]}55`);
    g.addColorStop(1, "transparent");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, width, height);
  }
  return canvas;
}

export function Cosmos({ universes, signal, mood }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const labelRefs = useRef(new Map<string, HTMLDivElement>());
  const universesRef = useRef(universes);
  const moodRef = useRef(mood);
  const burstRef = useRef(0);
  const dragRef = useRef({ active: false, x: 0, y: 0, yaw: 0, pitch: 0, spin: 0 });

  universesRef.current = universes;
  moodRef.current = mood;

  useEffect(() => {
    if (signal > 0) burstRef.current += 1;
  }, [signal]);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const ctx = context;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const { points, edges } = buildBrain();
    const projected = points.map(() => [0, 0, 0, 0] as [number, number, number, number]);
    const neuron = glowSprite("#8fdcff", 32);
    const pulseCool = glowSprite("#d98bff", 40);
    const pulseWarm = glowSprite("#ffd48a", 40);
    const moonSprite = glowSprite("#b9f3ff", 64);
    const galaxies = [galaxySprite(190, 11), galaxySprite(280, 23), galaxySprite(330, 37), galaxySprite(45, 51)];
    const starRng = mulberry32(99);
    const stars = Array.from({ length: 520 }, () => ({
      x: starRng(), y: starRng(), size: starRng() ** 3 * 1.8 + 0.3, phase: starRng() * Math.PI * 2, depth: 0.2 + starRng() * 0.8,
    }));

    let width = 0;
    let height = 0;
    let dpr = 1;
    let nebula = nebulaLayer(1, 1);
    let frame = 0;
    let lastBurst = burstRef.current;
    let vocal = 0;
    let flash = 0;
    let energy = 0.3;
    const pulses: Pulse[] = [];
    const comets: Comet[] = [];

    function resize() {
      const rect = wrap!.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = Math.round(width * dpr);
      canvas!.height = Math.round(height * dpr);
      nebula = nebulaLayer(Math.round(width / 2), Math.round(height / 2));
    }
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);

    function spawnPulse(warm: boolean) {
      pulses.push({ edge: Math.floor(Math.random() * edges.length), t: 0, speed: 0.02 + Math.random() * 0.035, forward: Math.random() < 0.5, warm });
    }

    function spawnComet() {
      const angle = Math.random() * Math.PI * 2;
      const distance = Math.max(width, height) * 0.7;
      const x = width / 2 + Math.cos(angle) * distance;
      const y = height / 2 + Math.sin(angle) * distance;
      const speed = 9 + Math.random() * 4;
      comets.push({ x, y, vx: -Math.cos(angle) * speed, vy: -Math.sin(angle) * speed, life: 1 });
    }

    function placeLabel(key: string, x: number, y: number, depth: number) {
      const el = labelRefs.current.get(key);
      if (!el) return;
      const margin = Math.min(70, width / 4);
      x = Math.max(margin, Math.min(width - margin, x));
      el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -140%)`;
      el.style.opacity = String(Math.max(0.35, Math.min(1, 1.25 - depth * 0.35)));
      el.style.zIndex = depth > 0 ? "1" : "3";
    }

    function draw(time: number) {
      const t = reducedMotion ? time * 0.08 : time;
      const currentMood = moodRef.current;
      const targetEnergy = { idle: 0.3, listening: 0.6, thinking: 1, speaking: 0.75 }[currentMood];
      energy += (targetEnergy - energy) * 0.03;
      if (burstRef.current !== lastBurst) {
        lastBurst = burstRef.current;
        flash = 1;
        spawnComet();
        for (let i = 0; i < 45; i += 1) spawnPulse(true);
      }
      // The brain pulses with the loudness of DEUS's voice.
      vocal += (voiceActivity.level - vocal) * 0.35;
      if (vocal > 0.05) {
        flash = Math.max(flash, vocal * 0.45);
        for (let i = 0; i < Math.round(vocal * 8); i += 1) spawnPulse(true);
      }
      flash *= 0.96;
      const drag = dragRef.current;
      if (!drag.active) {
        drag.yaw += drag.spin;
        drag.spin *= 0.95;
        drag.pitch *= 0.97;
      }

      const cx = width / 2;
      const cy = height * (width < 700 ? 0.4 : 0.42);
      const scale = Math.min(width * (width < 700 ? 0.34 : 0.26), height * 0.22);
      const detail = Math.min(1, scale / 190);
      // Orbits are squeezed horizontally so moons and galaxies stay on narrow screens.
      const orbitSpread = Math.min(1, (width / 2 - 50) / (2.9 * scale));
      // ...and tilted more steeply to keep them clear of the brain.
      const orbitLift = (1 - orbitSpread) * 0.45;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "#02010a";
      ctx.fillRect(0, 0, width, height);
      const drift = Math.sin(t * 0.00003) * 30;
      ctx.globalAlpha = 0.9;
      ctx.drawImage(nebula, -40 + drift, -40, width + 80, height + 80);
      ctx.globalAlpha = 1;

      ctx.globalCompositeOperation = "lighter";
      for (const star of stars) {
        const twinkle = 0.55 + 0.45 * Math.sin(t * 0.0015 * star.depth + star.phase);
        const sx = ((star.x * width + t * 0.004 * star.depth) % width + width) % width;
        ctx.fillStyle = `rgba(220, 230, 255, ${(0.25 + star.depth * 0.6) * twinkle})`;
        ctx.fillRect(sx, star.y * height, star.size, star.size);
      }

      // Aura around the brain — breathes faster while DEUS is thinking.
      const breath = 0.5 + 0.5 * Math.sin(t * (0.0012 + energy * 0.003));
      const auraRadius = scale * (1.9 + breath * 0.15 + flash * 0.4 + vocal * 0.35);
      const aura = ctx.createRadialGradient(cx, cy, 0, cx, cy, auraRadius);
      aura.addColorStop(0, currentMood === "listening"
        ? `rgba(60, 200, 255, ${0.2 + energy * 0.14 + flash * 0.2})`
        : `rgba(120, 90, 255, ${0.16 + energy * 0.14 + flash * 0.2})`);
      aura.addColorStop(0.45, `rgba(40, 120, 255, ${0.06 + energy * 0.06})`);
      aura.addColorStop(1, "transparent");
      ctx.fillStyle = aura;
      ctx.fillRect(cx - auraRadius, cy - auraRadius, auraRadius * 2, auraRadius * 2);

      // Mostly a side profile (the classic brain silhouette), slowly turning to reveal depth.
      const yaw = Math.PI / 2 + Math.sin(t * 0.00009) * 0.85 + drag.yaw;
      const pitch = -0.14 + Math.sin(t * 0.00017) * 0.05 + drag.pitch;
      const cosY = Math.cos(yaw);
      const sinY = Math.sin(yaw);
      const cosP = Math.cos(pitch);
      const sinP = Math.sin(pitch);

      const project = (x: number, y: number, z: number, rotate: boolean): [number, number, number, number] => {
        let rx = x;
        let rz = z;
        if (rotate) {
          rx = x * cosY + z * sinY;
          rz = -x * sinY + z * cosY;
        }
        const ry = y * cosP - rz * sinP;
        const depth = y * sinP + rz * cosP;
        const f = CAMERA / (CAMERA + depth);
        return [cx + rx * f * scale * (rotate ? 1 : orbitSpread), cy - ry * f * scale, depth, f];
      };

      // Orbiting bodies: universes as galaxies, SOPHIA and ROCKMAM as moons.
      const bodies: Array<{ key: string; x: number; y: number; depth: number; f: number; kind: "galaxy" | "moon"; index: number; active: boolean }> = [];
      const moons = [
        { key: "sophia", radius: 1.95, speed: 0.00022, offset: 0.4, tilt: 0.35 },
        { key: "rockmam", radius: 2.2, speed: -0.00016, offset: 2.6, tilt: -0.25 },
      ];
      for (const [index, moon] of moons.entries()) {
        const a = moon.offset + t * moon.speed;
        const [x, y, depth, f] = project(Math.cos(a) * moon.radius, Math.sin(a) * moon.radius * (moon.tilt + Math.sign(moon.tilt) * orbitLift), Math.sin(a) * moon.radius, false);
        bodies.push({ key: moon.key, x, y, depth, f, kind: "moon", index, active: true });
      }
      const list = universesRef.current;
      for (const [index, universe] of list.entries()) {
        const radius = 2.5 + (index % 3) * 0.3;
        const a = (index / Math.max(1, list.length)) * Math.PI * 2 + t * (0.00006 + (index % 2) * 0.00003);
        const [x, y, depth, f] = project(Math.cos(a) * radius, Math.sin(a) * radius * (0.18 + orbitLift) - 0.05, Math.sin(a) * radius * 0.8, false);
        bodies.push({ key: universe.id, x, y, depth, f, kind: "galaxy", index, active: universe.active });
      }

      const drawBody = (body: (typeof bodies)[number]) => {
        if (body.kind === "moon") {
          // While DEUS thinks, SOPHIA and ROCKMAM reason with it: they swell and link to the brain.
          const reasoning = currentMood === "thinking";
          const swell = reasoning ? 1.45 + Math.sin(t * 0.008 + body.index * Math.PI) * 0.2 : 1;
          if (reasoning) {
            const link = ctx.createLinearGradient(body.x, body.y, cx, cy);
            link.addColorStop(0, "rgba(185, 243, 255, 0.55)");
            link.addColorStop(1, "rgba(217, 139, 255, 0)");
            ctx.strokeStyle = link;
            ctx.lineWidth = 1.4 * body.f;
            ctx.beginPath();
            ctx.moveTo(body.x, body.y);
            ctx.lineTo(cx, cy);
            ctx.stroke();
          }
          const size = 30 * body.f * detail * swell;
          ctx.drawImage(moonSprite, body.x - size, body.y - size, size * 2, size * 2);
        } else {
          const size = (body.active ? 70 : 46) * body.f * Math.min(1, scale / 180);
          ctx.save();
          ctx.globalAlpha = body.active ? 0.95 : 0.4;
          ctx.translate(body.x, body.y);
          ctx.rotate(t * 0.0002 + body.index);
          ctx.scale(1, 0.55);
          ctx.drawImage(galaxies[body.index % galaxies.length], -size / 2, -size / 2, size, size);
          ctx.restore();
        }
        placeLabel(body.key, body.x, body.y, body.depth);
      };

      for (const body of bodies) if (body.depth > 0) drawBody(body);

      for (let i = 0; i < points.length; i += 1) {
        const p = points[i];
        projected[i] = project(p[0], p[1], p[2], true);
      }

      ctx.lineWidth = 0.6;
      ctx.strokeStyle = `rgba(110, 170, 255, ${0.07 + energy * 0.08 + flash * 0.1})`;
      ctx.beginPath();
      for (const [a, b] of edges) {
        ctx.moveTo(projected[a][0], projected[a][1]);
        ctx.lineTo(projected[b][0], projected[b][1]);
      }
      ctx.stroke();

      for (let i = 0; i < projected.length; i += 1) {
        const [x, y, depth, f] = projected[i];
        const shimmer = 0.6 + 0.4 * Math.sin(t * 0.003 + i * 1.7);
        ctx.globalAlpha = Math.max(0.12, Math.min(1, (0.75 - depth * 0.45) * shimmer));
        const size = (4 + energy * 3 + vocal * 3) * f * detail;
        ctx.drawImage(neuron, x - size, y - size, size * 2, size * 2);
      }
      ctx.globalAlpha = 1;

      const spawnRate = reducedMotion ? 0.05 : 0.5 + energy * 3;
      for (let i = 0; i < Math.floor(spawnRate + Math.random()); i += 1) spawnPulse(currentMood === "speaking");
      for (let i = pulses.length - 1; i >= 0; i -= 1) {
        const pulse = pulses[i];
        pulse.t += pulse.speed;
        if (pulse.t >= 1) {
          pulses.splice(i, 1);
          continue;
        }
        const [a, b] = edges[pulse.edge];
        const from = projected[pulse.forward ? a : b];
        const to = projected[pulse.forward ? b : a];
        const x = from[0] + (to[0] - from[0]) * pulse.t;
        const y = from[1] + (to[1] - from[1]) * pulse.t;
        const size = 9 * from[3] * detail;
        ctx.globalAlpha = Math.sin(pulse.t * Math.PI);
        ctx.drawImage(pulse.warm ? pulseWarm : pulseCool, x - size, y - size, size * 2, size * 2);
      }
      ctx.globalAlpha = 1;

      for (const body of bodies) if (body.depth <= 0) drawBody(body);

      for (let i = comets.length - 1; i >= 0; i -= 1) {
        const comet = comets[i];
        comet.x += comet.vx;
        comet.y += comet.vy;
        const distance = Math.hypot(comet.x - cx, comet.y - cy);
        if (distance < scale * 0.5) comet.life -= 0.08;
        if (comet.life <= 0) {
          comets.splice(i, 1);
          continue;
        }
        const tail = ctx.createLinearGradient(comet.x, comet.y, comet.x - comet.vx * 14, comet.y - comet.vy * 14);
        tail.addColorStop(0, `rgba(255, 230, 180, ${comet.life})`);
        tail.addColorStop(1, "transparent");
        ctx.strokeStyle = tail;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(comet.x, comet.y);
        ctx.lineTo(comet.x - comet.vx * 14, comet.y - comet.vy * 14);
        ctx.stroke();
        ctx.drawImage(pulseWarm, comet.x - 10, comet.y - 10, 20, 20);
      }

      placeLabel("deus", cx, cy + scale * 1.05, -1);
      frame = requestAnimationFrame(draw);
    }

    // Drag anywhere on the universe to turn the brain; it keeps spinning with inertia.
    const onDown = (event: PointerEvent) => {
      dragRef.current = { ...dragRef.current, active: true, x: event.clientX, y: event.clientY, spin: 0 };
      wrap.setPointerCapture(event.pointerId);
    };
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag.active) return;
      const dx = (event.clientX - drag.x) * 0.008;
      const dy = (event.clientY - drag.y) * 0.006;
      drag.yaw += dx;
      drag.spin = dx;
      drag.pitch = Math.max(-0.7, Math.min(0.7, drag.pitch - dy));
      drag.x = event.clientX;
      drag.y = event.clientY;
    };
    const onUp = () => { dragRef.current.active = false; };
    wrap.addEventListener("pointerdown", onDown);
    wrap.addEventListener("pointermove", onMove);
    wrap.addEventListener("pointerup", onUp);
    wrap.addEventListener("pointercancel", onUp);

    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      wrap.removeEventListener("pointerdown", onDown);
      wrap.removeEventListener("pointermove", onMove);
      wrap.removeEventListener("pointerup", onUp);
      wrap.removeEventListener("pointercancel", onUp);
    };
  }, []);

  const bindLabel = (key: string) => (el: HTMLDivElement | null) => {
    if (el) labelRefs.current.set(key, el);
    else labelRefs.current.delete(key);
  };

  return (
    <div className={`cosmos cosmos-${mood}`} ref={wrapRef}>
      <canvas ref={canvasRef} aria-hidden="true" />
      <div className="cosmos-labels">
        <div className="cosmic-label deus-label" ref={bindLabel("deus")}><span className="deus">DEUS</span></div>
        <div className="cosmic-label moon-label orbit orbit-a" ref={bindLabel("sophia")}><span>SOPHIA</span></div>
        <div className="cosmic-label moon-label orbit orbit-b" ref={bindLabel("rockmam")}><span>ROCKMAM</span></div>
        {universes.map((universe) => (
          <div className={`cosmic-label universe-label${universe.active ? "" : " dormant"}`} key={universe.id} ref={bindLabel(universe.id)}>
            <span>{universe.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
