import { CreatorStatus } from "./CreatorStatus";
import { SacredGeometry } from "./SacredGeometry";
import type { Pulse } from "../types";

type PulseHeaderProps = {
  pulse: Pulse | null;
  authenticated: boolean;
};

export function PulseHeader({ pulse, authenticated }: PulseHeaderProps) {
  const healthyServices = pulse?.status === "degraded" ? "5/6" : "6/6";

  return (
    <header className="exact-header">
      <section className="brand-mark">
        <SacredGeometry className="brand-geometry" />
        <div>
          <strong>THE CREATION <span>OS</span></strong>
          <em>LIVING CORE</em>
        </div>
      </section>
      <section className="pulse-center">
        <span>PULSE DO SISTEMA</span>
        <svg viewBox="0 0 240 36" aria-hidden="true">
          <path d="M0 18 H35 L42 17 L48 4 L55 29 L62 18 H92 L99 15 L104 21 L111 18 H139 L145 11 L151 27 L159 18 H190 L197 16 L202 20 L209 18 H240" />
        </svg>
        <strong>{healthyServices}</strong>
        <em>SERVIÇOS SAUDÁVEIS</em>
      </section>
      <CreatorStatus authenticated={authenticated} />
    </header>
  );
}
