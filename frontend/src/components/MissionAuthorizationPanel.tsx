import type { Mission, MissionAuthorization } from "../types";

type Props = {
  mission: Mission | null;
  authorization: MissionAuthorization | null;
  loading: boolean;
  error: string | null;
  onRequest: (missionId: string) => void;
  onApprove: (missionId: string) => void;
  onRevoke: (missionId: string) => void;
};

export function MissionAuthorizationPanel({ mission, authorization, loading, error, onRequest, onApprove, onRevoke }: Props) {
  if (!mission) return null;
  const actions = authorization?.scope_json.actions ?? [];
  const unauthorized = ["git_push", "deploy", "production_change", "use_real_financial_account"];
  const status = authorization?.status ?? "none";

  return (
    <section className="mission-authorization-panel" aria-label="Autorizacao da missao">
      <header>
        <strong>AUTORIZACAO DA MISSAO</strong>
        <span>{status}</span>
      </header>
      <article>
        <strong>{mission.title}</strong>
        <p>{mission.objective}</p>
        <dl>
          <div>
            <dt>Projeto</dt>
            <dd>{authorization?.project_id ?? "local"}</dd>
          </div>
          <div>
            <dt>Estado</dt>
            <dd>{status}</dd>
          </div>
          <div>
            <dt>Tarefas</dt>
            <dd>monitoradas</dd>
          </div>
        </dl>
      </article>
      <div className="mission-auth-list">
        <strong>Escopo autorizado</strong>
        <span>{actions.length ? actions.slice(0, 4).join(", ") : "aguardando solicitacao"}</span>
      </div>
      <div className="mission-auth-list">
        <strong>Acoes nao autorizadas</strong>
        <span>{unauthorized.join(", ")}</span>
      </div>
      {status === "none" ? (
        <button type="button" disabled={loading} onClick={() => onRequest(mission.id)}>
          Solicitar autorizacao
        </button>
      ) : null}
      {status === "pending" ? (
        <button type="button" disabled={loading} onClick={() => onApprove(mission.id)}>
          AUTORIZAR MISSAO
        </button>
      ) : null}
      {status === "authorized" ? (
        <>
          <p className="mission-auth-ok">MISSAO AUTORIZADA</p>
          <button type="button" disabled={loading} onClick={() => onRevoke(mission.id)}>
            Revogar
          </button>
        </>
      ) : null}
      {error ? <p className="mission-auth-error">{error}</p> : null}
    </section>
  );
}
