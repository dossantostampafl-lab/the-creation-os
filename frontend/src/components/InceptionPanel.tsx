import { DEMO_VISUAL_DATA } from "../data/universeLayout";
import type { Inception } from "../types";

type InceptionPanelProps = {
  inceptions: Inception[];
};

export function InceptionPanel({ inceptions }: InceptionPanelProps) {
  return (
    <aside className="inception-panel">
      <header>
        <strong>INCEPTIONS PENDENTES</strong>
        <span>{inceptions.length}</span>
      </header>
      {inceptions.slice(0, 2).map((item) => (
        <article key={item.id} data-source={item.conversation_id === DEMO_VISUAL_DATA ? DEMO_VISUAL_DATA : "API"}>
          <strong>{item.id.startsWith("INC-") ? item.id : `INC-${item.id.slice(0, 4)}`}</strong>
          <span>{item.status}</span>
          <p>{item.title}</p>
        </article>
      ))}
      <button type="button">VER TODAS</button>
    </aside>
  );
}
