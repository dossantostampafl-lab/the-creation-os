import type { Inception, Mission } from "../types";

type NeedlesProps = {
  inceptions: Inception[];
  missions: Mission[];
  loadState: string;
  dataError: string | null;
};

export function Needles({ inceptions, missions, loadState, dataError }: NeedlesProps) {
  const showInceptions = inceptions.length > 0;
  const showMissions = missions.length > 0;
  const showStatus = dataError || loadState === "loading" || loadState === "empty" || showInceptions || showMissions;

  if (!showStatus) return null;

  return (
    <aside className="needles">
      {dataError && <p className="needle warning">{dataError}</p>}
      {loadState === "loading" && <p className="needle">Synchronizing real backend signals...</p>}
      {loadState === "empty" && <p className="needle">Backend reachable. No active Creator data returned.</p>}
      {showInceptions && (
        <section className="needle-cluster">
          <strong>Pending Inceptions</strong>
          {inceptions.slice(0, 3).map((item) => (
            <span key={item.id}>{item.title} / {item.status}</span>
          ))}
        </section>
      )}
      {showMissions && (
        <section className="needle-cluster">
          <strong>Missions</strong>
          {missions.slice(0, 3).map((item) => (
            <span key={item.id}>{item.title} / {item.status}</span>
          ))}
        </section>
      )}
    </aside>
  );
}
