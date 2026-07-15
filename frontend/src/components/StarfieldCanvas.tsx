import { useEffect, useRef } from "react";

type Star = {
  x: number;
  y: number;
  radius: number;
  alpha: number;
  speed: number;
  gold: boolean;
};

export function StarfieldCanvas() {
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
        speed: Math.random() * 0.18 + 0.03,
        gold: Math.random() > 0.86,
      }));
    }

    function draw() {
      frame += 0.01;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      ctx.fillStyle = "#02040a";
      ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);

      for (const star of stars) {
        star.y += star.speed;
        if (star.y > window.innerHeight + 4) star.y = -4;
        const pulse = Math.sin(frame * (star.gold ? 1.8 : 1.1) + star.x) * 0.28;
        ctx.beginPath();
        ctx.fillStyle = star.gold
          ? `rgba(255, 176, 60, ${star.alpha + pulse})`
          : `rgba(220, 241, 255, ${star.alpha + pulse})`;
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      animation = window.requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      window.cancelAnimationFrame(animation);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="starfield-canvas" aria-hidden="true" />;
}
