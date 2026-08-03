import { useMemo, useState } from "react";
import type { Agent, Inception, Mission, Opportunity, Universe } from "../types";
import type { RequestedPanel } from "../appLogic";

type SearchPanelProps = {
  missions: Mission[];
  inceptions: Inception[];
  opportunities: Opportunity[];
  agents: Agent[];
  universes: Universe[];
  onOpenPanel: (panel: RequestedPanel) => void;
};

type SearchResult = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  panel: RequestedPanel;
};

// Client-side substring search over data already loaded from the real API — there is
// no backend search endpoint (confirmed absent), so this filters what is already in
// memory rather than fabricating a network search that doesn't exist.
function buildResults({ missions, inceptions, opportunities, agents, universes }: Omit<SearchPanelProps, "onOpenPanel">): SearchResult[] {
  return [
    ...missions.map((item) => ({ id: item.id, kind: "Missao", title: item.title, detail: item.status, panel: "missions" as const })),
    ...inceptions.map((item) => ({ id: item.id, kind: "Inception", title: item.title, detail: item.status, panel: "inceptions" as const })),
    ...opportunities.map((item) => ({ id: item.id, kind: "Oportunidade", title: item.title, detail: `${item.universe} / ${item.status}`, panel: "opportunities" as const })),
    ...agents.map((item) => ({ id: item.id, kind: "Agente", title: item.name, detail: `${item.universe} / ${item.status}`, panel: "universes" as const })),
    ...universes.map((item) => ({ id: item.id, kind: "Universo", title: item.name, detail: item.active ? "ativo" : "inativo", panel: "universes" as const })),
  ];
}

export function SearchPanel({ missions, inceptions, opportunities, agents, universes, onOpenPanel }: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const allResults = useMemo(
    () => buildResults({ missions, inceptions, opportunities, agents, universes }),
    [missions, inceptions, opportunities, agents, universes],
  );
  const normalizedQuery = query.trim().toLowerCase();
  const results = normalizedQuery
    ? allResults.filter((item) => item.title.toLowerCase().includes(normalizedQuery) || item.detail.toLowerCase().includes(normalizedQuery))
    : [];

  return (
    <section className="search-panel" aria-label="Busca">
      <header>
        <strong>BUSCA</strong>
        <span>{allResults.length} itens indexados</span>
      </header>
      <input
        type="text"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Buscar missoes, inceptions, oportunidades, agentes, universos..."
        aria-label="Termo de busca"
        autoFocus
      />
      {!normalizedQuery ? <p className="search-muted">Digite para buscar no que ja foi carregado da API.</p> : null}
      {normalizedQuery && results.length === 0 ? <p className="search-muted">Nenhum resultado para "{query}".</p> : null}
      {results.slice(0, 12).map((result) => (
        <button key={`${result.kind}-${result.id}`} type="button" className="search-result" onClick={() => onOpenPanel(result.panel)}>
          <span className="search-result-kind">{result.kind}</span>
          <strong>{result.title}</strong>
          <span className="search-result-detail">{result.detail}</span>
        </button>
      ))}
    </section>
  );
}
