import type { CSSProperties } from "react";
import type { Agent, Universe } from "../types";

type CoreDefinition = {
  id: "sophia" | "rockmam";
  label: string;
  role: string;
  description: string;
  xPercent: number;
  yPercent: number;
  tone: "violet" | "gold" | "blue";
  icon: "leaf" | "infinity";
};

// SOPHIA and ROCKMAM have no Agents of their own in the real data model (unlike
// Universes, which have real agents.filter(...) counts below) — no "N AGENTES"
// line is shown for them so nothing here is a fabricated number.
const CORES: CoreDefinition[] = [
  { id: "sophia", label: "SOPHIA", role: "SABEDORIA", description: "Compreende o contexto", xPercent: 24, yPercent: 19, tone: "violet", icon: "leaf" },
  { id: "rockmam", label: "ROCKMAM", role: "POSSIBILIDADE", description: "Avalia o que pode ser", xPercent: 76, yPercent: 19, tone: "blue", icon: "infinity" },
];

// Kept to the left/right columns (12%/88%) so cards never enter the
// horizontal band the conversation dock and Criador core cards occupy
// around center (dock: ~29%-71% x, ~80%-88% y; SOPHIA/ROCKMAM cores: ~19% y).
const UNIVERSE_SLOTS: { xPercent: number; yPercent: number }[] = [
  { xPercent: 12, yPercent: 46 },
  { xPercent: 88, yPercent: 46 },
  { xPercent: 12, yPercent: 68 },
  { xPercent: 88, yPercent: 68 },
  { xPercent: 12, yPercent: 30 },
  { xPercent: 88, yPercent: 30 },
];

const UNIVERSE_ICON: Record<string, string> = {
  knowledge: "book",
  engineering: "box",
  security: "shield",
  vision: "eye",
  design: "palette",
  business: "briefcase",
  marketing: "megaphone",
  legal: "scale",
  finance: "coin",
  automation: "cog",
  communication: "chat",
  evolution: "leaf",
};

const UNIVERSE_DESCRIPTION: Record<string, string> = {
  knowledge: "Compreensão e memória",
  engineering: "Constrói e mantém o sistema",
  security: "Protege, audita e mitiga riscos",
  vision: "Observa direção e propósito",
  design: "Forma e experiência",
  business: "Modelo e sustentação",
  marketing: "Alcance e narrativa",
  legal: "Conformidade e limites",
  finance: "Recursos e sustentação",
  automation: "Sustenta, escala e mantém o sistema",
  communication: "Conecta, observa e aprende com o todo",
  evolution: "Pesquisa, melhora e expande capacidades",
};

function Icon({ name }: { name: string }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.4 } as const;
  switch (name) {
    case "book":
      return (
        <svg {...common}>
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5V5.5Z" strokeLinejoin="round" />
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3" />
        </svg>
      );
    case "shield":
      return (
        <svg {...common}>
          <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z" strokeLinejoin="round" />
        </svg>
      );
    case "chat":
      return (
        <svg {...common}>
          <path d="M4 5h16v11H8l-4 4V5Z" strokeLinejoin="round" />
        </svg>
      );
    case "leaf":
      return (
        <svg {...common}>
          <path d="M5 19c8 0 14-6 14-14-8 0-14 6-14 14Z" strokeLinejoin="round" />
          <path d="M5 19c2-4 5-7 9-9" />
        </svg>
      );
    case "infinity":
      return (
        <svg {...common}>
          <path d="M8 8a4 4 0 1 0 0 8c2.5 0 3.5-1.8 4-4s1.5-4 4-4a4 4 0 1 1 0 8c-2.5 0-3.5-1.8-4-4s-1.5-4-4-4Z" strokeLinejoin="round" />
        </svg>
      );
    case "cog":
      return (
        <svg {...common}>
          <path d="M4 8h3M17 8h3M4 16h16" strokeLinecap="round" />
          <rect x="4" y="4" width="16" height="16" rx="3" />
        </svg>
      );
    case "box":
      return (
        <svg {...common}>
          <path d="M4 7l8-4 8 4-8 4-8-4Z" strokeLinejoin="round" />
          <path d="M4 7v10l8 4 8-4V7" strokeLinejoin="round" />
          <path d="M12 11v10" />
        </svg>
      );
    case "eye":
      return (
        <svg {...common}>
          <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z" strokeLinejoin="round" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "palette":
      return (
        <svg {...common}>
          <path d="M12 3a9 9 0 1 0 0 18c1.2 0 2-1 2-2 0-.6-.3-1-.6-1.4-.3-.3-.5-.7-.5-1.1 0-.9.7-1.5 1.6-1.5H17a3 3 0 0 0 3-3c0-5-3.6-9-8-9Z" />
        </svg>
      );
    case "briefcase":
      return (
        <svg {...common}>
          <rect x="3" y="7" width="18" height="12" rx="2" />
          <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </svg>
      );
    case "megaphone":
      return (
        <svg {...common}>
          <path d="M3 10v4l14 4V6L3 10Z" strokeLinejoin="round" />
          <path d="M17 9v6" />
        </svg>
      );
    case "scale":
      return (
        <svg {...common}>
          <path d="M12 3v18M6 7h12M4 7l3 6a3 3 0 0 0 6 0L10 7M14 7l3 6a3 3 0 0 0 6 0l-3-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "coin":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v10M9 9.5c0-1 1-1.5 3-1.5s3 .5 3 1.5-1 1.5-3 1.5-3 .5-3 1.5 1 1.5 3 1.5 3-.5 3-1.5" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

type UniverseConstellationLabelsProps = {
  agents: Agent[];
  universes: Universe[];
  onSelectPanel: (panel: "universes") => void;
};

export function UniverseConstellationLabels({ agents, universes, onSelectPanel }: UniverseConstellationLabelsProps) {
  const active = universes.filter((universe) => universe.active);
  const inactive = universes.filter((universe) => !universe.active);

  function agentCount(code: string) {
    return agents.filter((agent) => agent.enabled && agent.universe === code).length;
  }

  return (
    <section className="constellation-labels" aria-label="Nucleos e universos do sistema">
      {CORES.map((core) => (
        <article
          key={core.id}
          className={`constellation-card core-card tone-${core.tone}`}
          style={{ "--card-x": `${core.xPercent}%`, "--card-y": `${core.yPercent}%` } as CSSProperties}
        >
          <span className="constellation-icon" aria-hidden="true">
            <Icon name={core.icon} />
          </span>
          <span className="constellation-body">
            <strong>{core.label}</strong>
            <span className="constellation-role">{core.role}</span>
            <p>{core.description}</p>
          </span>
        </article>
      ))}

      {active.map((universe, index) => {
        const slot = UNIVERSE_SLOTS[index % UNIVERSE_SLOTS.length];
        const icon = UNIVERSE_ICON[universe.code] ?? "default";
        const description = UNIVERSE_DESCRIPTION[universe.code] ?? "Universo ativo";
        return (
          <button
            key={universe.id}
            type="button"
            className="constellation-card universe-card is-active"
            style={{ "--card-x": `${slot.xPercent}%`, "--card-y": `${slot.yPercent}%` } as CSSProperties}
            onClick={() => onSelectPanel("universes")}
          >
            <span className="constellation-icon" aria-hidden="true">
              <Icon name={icon} />
            </span>
            <span className="constellation-body">
              <strong>{universe.name}</strong>
              <p>{description}</p>
              <em>{agentCount(universe.code)} AGENTES</em>
            </span>
          </button>
        );
      })}

      {inactive.length > 0 ? (
        <button type="button" className="constellation-inactive-strip" onClick={() => onSelectPanel("universes")}>
          <span>{inactive.length} universos inativos</span>
          <span className="constellation-inactive-dots" aria-hidden="true">
            {inactive.map((universe) => (
              <i key={universe.id} title={universe.name} />
            ))}
          </span>
        </button>
      ) : null}
    </section>
  );
}
