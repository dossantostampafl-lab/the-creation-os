import type { Agent } from "../types";
import type { UniverseVisual } from "../data/universeLayout";

type UniverseGalaxyProps = {
  universe: UniverseVisual;
  agents: Agent[];
  missionActive: boolean;
};

export function UniverseGalaxy({ universe, agents, missionActive }: UniverseGalaxyProps) {
  const count = agents.length;
  const points = Array.from({ length: count }, (_, index) => index);

  return (
    <article
      className={`universe-galaxy exact-galaxy ${universe.id}`}
      style={{
        left: `${universe.left}%`,
        top: `${universe.top}%`,
        "--galaxy-color": universe.color,
        "--galaxy-soft": universe.colorSoft,
        "--agent-count": count,
        "--galaxy-duration": `${Math.max(20, 42 - count * 1.5)}s`,
      } as React.CSSProperties}
      data-source="API"
      data-agent-active={missionActive && count > 0}
      data-empty={count === 0}
    >
      <div className="galaxy-icon">{iconFor(universe.icon)}</div>
      <div className="spiral-disk">
        <span className="spiral-core" />
        {points.map((point) => (
          <i key={point} style={{ "--star-index": point } as React.CSSProperties} />
        ))}
      </div>
      <div className="galaxy-label">
        <strong>{universe.title}</strong>
        <span>{count} {count === 1 ? "AGENTE" : "AGENTES"}</span>
        <p>{universe.description}</p>
      </div>
    </article>
  );
}

function iconFor(icon: string) {
  switch (icon) {
    case "book":
      return "□";
    case "leaf":
      return "◒";
    case "code":
      return "</>";
    case "shield":
      return "⬟";
    case "users":
      return "●●";
    case "box":
      return "◇";
    default:
      return "✦";
  }
}
