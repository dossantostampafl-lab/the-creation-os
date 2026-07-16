import type { ChronicleEntry } from "../types";

type ChronicleRibbonProps = {
  entries: ChronicleEntry[];
};

export function ChronicleRibbon({ entries }: ChronicleRibbonProps) {
  return (
    <footer className="exact-chronicle">
      <section className="chronicle-origin">É MALKUTH · MANIFESTADO</section>
      <strong>CHRONICLES</strong>
      <div className="chronicle-events">
        {entries.length === 0 ? <article><time>--:--:--</time><span>Chronicle sem eventos retornados pela API</span></article> : null}
        {entries.map((entry) => (
          <article key={entry.id} data-source="API">
            <time>{entry.aggregate_type.includes(":") ? entry.aggregate_type : new Date(entry.created_at).toLocaleTimeString("pt-BR")}</time>
            <span>{entry.actor_role}: {entry.event_type}</span>
          </article>
        ))}
      </div>
      <button type="button">VER TUDO →</button>
    </footer>
  );
}
