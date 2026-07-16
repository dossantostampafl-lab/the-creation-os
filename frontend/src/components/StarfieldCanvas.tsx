import { useEffect, useRef } from "react";

type Star = {
  x: number;
  y: number;
  radius: number;
  alpha: number;
  speed: number;
  gold: boolean;
  phase: number;
  depth: number;
};

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
  hue: "gold" | "blue" | "green";
};

type StarfieldCanvasProps = {
  activity: number;
  health: string;
  activeAgents: number;
  runningMissions: number;
  pendingInceptions: number;
};

export function StarfieldCanvas({ activity, health, activeAgents, runningMissions, pendingInceptions }: StarfieldCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const context = canvas.getContext("2d");
    if (!context) return undefined;
    const surface = canvas;
    const ctx = context;

    let frame = 0;
    let animation = 0;
    let stars: Star[] = [];
    let particles: Particle[] = [];
    let suspended = document.hidden;

    const particleBudget = Math.min(170, 28 + activeAgents * 4 + runningMissions * 24 + pendingInceptions * 10);
    const velocity = 0.55 + activity * 1.4;

    function resize() {
      const ratio = window.devicePixelRatio || 1;
      surface.width = Math.floor(window.innerWidth * ratio);
      surface.height = Math.floor(window.innerHeight * ratio);
      surface.style.width = `${window.innerWidth}px`;
      surface.style.height = `${window.innerHeight}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      stars = Array.from({ length: 1400 }, () => ({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        radius: Math.random() * 1.25 + 0.18,
        alpha: Math.random() * 0.72 + 0.18,
        speed: (Math.random() * 0.18 + 0.03) * velocity,
        gold: Math.random() > 0.86,
        phase: Math.random() * Math.PI * 2,
        depth: Math.random() * 0.72 + 0.28,
      }));
      particles = [];
    }

    function spawnParticle() {
      const missionHue = runningMissions > 0 ? "gold" : pendingInceptions > 0 ? "blue" : health === "healthy" ? "green" : "gold";
      particles.push({
        x: window.innerWidth * (0.18 + Math.random() * 0.64),
        y: window.innerHeight * (0.78 - Math.random() * 0.56),
        vx: (Math.random() - 0.5) * (0.34 + activity),
        vy: -(0.16 + Math.random() * (0.42 + activity * 0.62)),
        life: 0,
        maxLife: 120 + Math.random() * 100,
        hue: missionHue,
      });
    }

    function drawParticles() {
      while (particles.length < particleBudget && Math.random() < 0.42 + activity * 0.32) {
        spawnParticle();
      }
      particles = particles.filter((particle) => particle.life < particle.maxLife);
      for (const particle of particles) {
        particle.life += 1;
        particle.x += particle.vx;
        particle.y += particle.vy;
        const fade = 1 - particle.life / particle.maxLife;
        const color =
          particle.hue === "green"
            ? `rgba(134, 244, 196, ${fade * 0.32})`
            : particle.hue === "blue"
              ? `rgba(113, 183, 255, ${fade * 0.34})`
              : `rgba(255, 196, 84, ${fade * 0.36})`;
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.arc(particle.x, particle.y, 1.2 + fade * 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function draw(time = 0) {
      if (suspended) return;
      frame += 0.01;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      ctx.fillStyle = "#02040a";
      ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);

      for (const star of stars) {
        star.y += star.speed * (0.68 + star.depth * 0.7);
        star.x += Math.sin(frame + star.phase) * 0.018 * star.depth;
        if (star.y > window.innerHeight + 4) star.y = -4;
        const pulse = Math.sin(time * 0.002 * (star.gold ? 1.8 : 1.1) + star.phase) * (0.18 + activity * 0.18);
        ctx.beginPath();
        ctx.fillStyle = star.gold
          ? `rgba(255, 176, 60, ${Math.max(0.05, star.alpha + pulse)})`
          : `rgba(220, 241, 255, ${Math.max(0.05, star.alpha + pulse)})`;
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fill();
      }
      drawParticles();

      animation = window.requestAnimationFrame(draw);
    }

    function handleVisibility() {
      suspended = document.hidden;
      if (!suspended) {
        animation = window.requestAnimationFrame(draw);
      }
    }

    resize();
    draw();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.cancelAnimationFrame(animation);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [activity, activeAgents, health, pendingInceptions, runningMissions]);

  return <canvas ref={canvasRef} className="starfield-canvas" aria-hidden="true" />;
}
