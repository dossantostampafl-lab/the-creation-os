import type { AutomationExecution, CapabilityFramework } from "../types";

type CapabilityPanelProps = {
  capabilities: CapabilityFramework[];
  loading: boolean;
  error: string | null;
  result: AutomationExecution | null;
  onEnable: (capabilityId: string) => void;
  onDisable: (capabilityId: string) => void;
  onExecute: () => void;
};

export function CapabilityPanel({
  capabilities,
  loading,
  error,
  result,
  onEnable,
  onDisable,
  onExecute,
}: CapabilityPanelProps) {
  const restCapability = capabilities.find((item) => item.capability_id === "rest.restricted.request");
  const visibleCapabilities = capabilities.slice(0, 4);
  const executionBlocked = loading || !restCapability?.enabled;

  return (
    <section className="capability-panel" aria-label="Capabilities e automations">
      <header>
        <strong>CAPABILITIES</strong>
        <span>{capabilities.length}</span>
      </header>
      {loading ? <p className="capability-muted">Carregando estado real...</p> : null}
      {!loading && capabilities.length === 0 ? <p className="capability-muted">Nenhuma capability registrada.</p> : null}
      {visibleCapabilities.map((capability) => (
        <article key={capability.capability_id}>
          <div>
            <strong>{capability.name}</strong>
            <span>
              {capability.connector_id}/{capability.connector_capability}
            </span>
          </div>
          <button
            type="button"
            disabled={loading || capability.mandatory}
            onClick={() =>
              capability.enabled ? onDisable(capability.capability_id) : onEnable(capability.capability_id)
            }
          >
            {capability.enabled ? "ON" : "OFF"}
          </button>
        </article>
      ))}
      <button className="automation-action" type="button" disabled={executionBlocked} onClick={onExecute}>
        Executar REST seguro
      </button>
      {error ? <p className="capability-error">{error}</p> : null}
      {result ? (
        <p className="capability-result">
          {result.status} · {result.connector_id}/{result.capability}
        </p>
      ) : null}
    </section>
  );
}
