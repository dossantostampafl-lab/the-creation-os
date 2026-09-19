import type { ChronicleEntry } from "../types";

type ChronicleTickerProps = {
  entries: ChronicleEntry[];
  onOpenFull: () => void;
};

// Every key below is a real event_type emitted by backend/app/{services,repositories}
// (audited against the actual add_event(...) call sites, not guessed) — the previous
// map used dot-notation keys ("mission.decided") that never matched the real
// underscore-based values ("mission_decided"), so it silently fell through to the
// raw-string fallback. Keys with a literal "." below are real too (mission
// authorization, capability governance, perception and opportunity events use
// dot-notation by design in the backend); the two styles coexist in the real stream.
const EVENT_LABEL: Record<string, string> = {
  conversation_created: "GOD registrou nova conversa",
  conversation_message_added: "GOD recebeu nova mensagem",
  conversation_closed: "Conversa encerrada",
  conversation_archived: "Conversa arquivada",
  god_conversation_interaction_completed: "GOD concluiu a interação",
  sophia_understanding_created: "SOPHIA compreendeu novo contexto",
  rockmam_possibility_assessment_created: "ROCKMAM avaliou uma possibilidade",
  inception_created: "Inception proposto",
  inception_submitted: "Inception enviado para decisão",
  inception_approved: "Inception aprovado pelo Criador",
  inception_rejected: "Inception rejeitado pelo Criador",
  inception_cancelled: "Inception cancelado",
  mission_created: "Nova missão criada",
  mission_planned: "Missão planejada",
  mission_validated: "Missão validada",
  mission_authorized: "Missão autorizada",
  mission_cancelled: "Missão cancelada",
  mission_distributed: "Missão distribuída para execução",
  mission_executing: "Missão em execução",
  mission_failed: "Missão falhou",
  mission_consolidated: "Missão consolidada",
  mission_decided: "Missão decidida",
  mission_manifested: "MALKUTH manifestou o resultado",
  "mission.authorization.requested": "Autorização de missão solicitada",
  "mission.authorization.approved": "Autorização de missão aprovada",
  "mission.authorization.suspended": "Autorização de missão suspensa",
  "mission.authorization.revoked": "Autorização de missão revogada",
  "mission.authorization.completed": "Autorização de missão concluída",
  "mission.action.authorized": "Ação de missão autorizada",
  "mission.action.denied": "Ação de missão negada",
  "mission.scope.exceeded": "Ação bloqueada por exceder escopo",
  task_created: "Nova tarefa criada",
  task_ready: "Tarefa pronta para execução",
  task_updated: "Tarefa atualizada",
  task_dependency_added: "Dependência de tarefa adicionada",
  task_dependency_removed: "Dependência de tarefa removida",
  cycle_creation_blocked: "Dependência circular bloqueada",
  mission_plan_created: "ENGENHARIA concluiu planejamento",
  capability_state_changed: "Capability alterada",
  "capability.execution.authorized": "Execução de capability autorizada",
  "capability.execution.denied": "Execução de capability negada",
  automation_connector_executed: "Automação executada via conector",
  "voice.synthesis.requested": "Síntese de voz solicitada",
  "voice.synthesis.succeeded": "Voz de GOD sintetizada",
  "voice.synthesis.failed": "Falha na síntese de voz",
  creator_memory_recorded: "Memória do Criador registrada",
  "observation.ingested": "Nova observação percebida",
  "observation.rejected": "Observação rejeitada",
  "observation.duplicate_ignored": "Observação duplicada ignorada",
  "observation.normalized": "Observação normalizada",
  "opportunity.discovery.triggered": "Descoberta de oportunidades disparada",
  "opportunity.ranking.updated": "Ranking de oportunidades atualizado",
  "opportunity.approved": "Oportunidade aprovada pelo Criador",
  "opportunity.rejected": "Oportunidade rejeitada pelo Criador",
  "opportunity.expired": "Oportunidade expirou",
  "opportunity.converted_to_inception": "Oportunidade convertida em Inception",
  "opportunity.review.requested": "Revisão de oportunidade solicitada",
  "opportunity.execution.denied": "Execução de oportunidade negada",
  "perception.source.enabled": "Fonte de percepção ativada",
  "perception.source.disabled": "Fonte de percepção desativada",
  "perception.source.created": "Fonte de percepção criada",
  "perception.collection.started": "Coleta de percepção iniciada",
  "perception.collection.succeeded": "Coleta de percepção concluída",
  "perception.collection.failed": "Coleta de percepção falhou",
  "perception.collection.skipped": "Coleta de percepção ignorada",
  "perception.checkpoint.updated": "Checkpoint de percepção atualizado",
  "source.collection.resumed": "Fonte de percepção retomada",
  "source.collection.suspended": "Fonte de percepção suspensa",
  "creator.notification.created": "Nova notificação para o Criador",
  "creator.notification.read": "Notificação lida",
  "creator.notification.acknowledged": "Notificação confirmada",
};

type TickerCategory = "core" | "sophia" | "rockmam" | "engineering" | "security" | "perception";

function categorize(eventType: string): TickerCategory {
  if (eventType.startsWith("sophia_")) return "sophia";
  if (eventType.startsWith("rockmam_")) return "rockmam";
  if (eventType.startsWith("conversation") || eventType.startsWith("god_") || eventType.startsWith("creator_memory")) return "core";
  if (eventType.startsWith("capability") || eventType.startsWith("mission.authorization") || eventType.startsWith("mission.action") || eventType.startsWith("mission.scope")) return "security";
  if (eventType.startsWith("perception") || eventType.startsWith("source.collection") || eventType.startsWith("opportunity") || eventType.startsWith("observation") || eventType.startsWith("creator.notification")) return "perception";
  return "engineering";
}

function CategoryIcon({ category }: { category: TickerCategory }) {
  const common = { width: 13, height: 13, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6 } as const;
  switch (category) {
    case "core":
      return (
        <svg {...common}>
          <path d="M12 2l2.2 6.8H21l-5.6 4.1 2.2 6.9L12 15.7l-5.6 4.1 2.2-6.9L3 8.8h6.8L12 2Z" strokeLinejoin="round" />
        </svg>
      );
    case "sophia":
      return (
        <svg {...common}>
          <path d="M5 19c8 0 14-6 14-14-8 0-14 6-14 14Z" strokeLinejoin="round" />
          <path d="M5 19c2-4 5-7 9-9" />
        </svg>
      );
    case "rockmam":
      return (
        <svg {...common}>
          <path d="M8 8a4 4 0 1 0 0 8c2.5 0 3.5-1.8 4-4s1.5-4 4-4a4 4 0 1 1 0 8c-2.5 0-3.5-1.8-4-4s-1.5-4-4-4Z" strokeLinejoin="round" />
        </svg>
      );
    case "security":
      return (
        <svg {...common}>
          <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z" strokeLinejoin="round" />
        </svg>
      );
    case "perception":
      return (
        <svg {...common}>
          <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z" strokeLinejoin="round" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path d="M4 7l8-4 8 4-8 4-8-4Z" strokeLinejoin="round" />
          <path d="M4 7v10l8 4 8-4V7" strokeLinejoin="round" />
          <path d="M12 11v10" />
        </svg>
      );
  }
}

function humanizeEventType(eventType: string): string {
  return eventType
    .split(/[._]/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function describeEvent(entry: ChronicleEntry): string {
  return EVENT_LABEL[entry.event_type] ?? `${entry.actor_role}: ${humanizeEventType(entry.event_type)}`;
}

function formatTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--:--:--";
  return parsed.toLocaleTimeString("pt-BR", { hour12: false });
}

export function ChronicleTicker({ entries, onOpenFull }: ChronicleTickerProps) {
  const recent = entries.slice(0, 8);

  return (
    <footer className="chronicle-ticker" aria-label="Cronicas recentes do sistema">
      <div className="chronicle-ticker-head">
        <span className="chronicle-ticker-dot" aria-hidden="true" />
        <strong>CRÔNICAS DO SISTEMA</strong>
      </div>
      <div className="chronicle-ticker-track">
        {recent.length === 0 ? (
          <article className="chronicle-ticker-item">
            <time>--:--:--</time>
            <span>Sem eventos retornados pela API ainda.</span>
          </article>
        ) : (
          recent.map((entry) => {
            const category = categorize(entry.event_type);
            return (
              <article className={`chronicle-ticker-item tone-${category}`} key={entry.id}>
                <span className="chronicle-ticker-icon" aria-hidden="true">
                  <CategoryIcon category={category} />
                </span>
                <time>{formatTime(entry.created_at)}</time>
                <span>{describeEvent(entry)}</span>
              </article>
            );
          })
        )}
      </div>
      <button type="button" className="chronicle-ticker-more" onClick={onOpenFull}>
        VER HISTÓRICO COMPLETO →
      </button>
    </footer>
  );
}
