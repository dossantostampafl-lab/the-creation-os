import { newRequestId } from './requestId';
import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import {
  CREATOR_CONVERSATION_KEY,
  converseWithDeus,
  createConversation,
  decideInception,
  fetchConversationMessages,
  fetchInception,
  fetchInceptions,
  cancelMission,
  fetchMission,
  startMission,
} from "./api";
import type { ConversationMessage, Inception } from "./api";
import type { CosmosMood } from "./Cosmos";
import { TrinityProposal, proposalStage } from "./TrinityProposal";
import type { Proposal, ProposalAction } from "./TrinityProposal";
import { useDeusVoiceSession } from "./voice-session/useDeusVoiceSession";
import "./CreatorConsole.css";

type Props = {
  enabled: boolean;
  onMoodChange?: (mood: CosmosMood) => void;
};

const CONVERSATION_KEY = CREATOR_CONVERSATION_KEY;

type Entry = { kind: "message"; at: string; message: ConversationMessage } | { kind: "proposal"; at: string; proposal: Proposal };

/** Messages and Trinity proposals in the order they happened; a proposal follows the exchange that raised it. */
function timeline(messages: ConversationMessage[], proposals: Proposal[]): Entry[] {
  const entries: Entry[] = [
    ...messages.map((message) => ({ kind: "message" as const, at: message.created_at, message })),
    ...proposals.map((proposal) => ({ kind: "proposal" as const, at: proposal.inception.proposed_at, proposal })),
  ];
  return entries.sort((a, b) => Date.parse(a.at) - Date.parse(b.at) || (a.kind === b.kind ? 0 : a.kind === "message" ? -1 : 1));
}

async function loadProposal(inception: Inception): Promise<Proposal> {
  const missionId = inception.trinity_assessment.mission_id;
  return { inception, mission: missionId ? await fetchMission(missionId) : null };
}

export function CreatorConsole({ enabled, onMoodChange }: Props) {
  const [conversationId, setConversationId] = useState(() => window.localStorage.getItem(CONVERSATION_KEY));
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [deciding, setDeciding] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const creatingConversation = useRef(false);
  const voiceSession = useDeusVoiceSession({
    enabled: enabled && Boolean(conversationId),
    conversationId,
    onWake: () => setError(null),
    onTranscript: (text, turnId, sessionId) => {
      setInput("");
      const localId = `local-creator-voice-${sessionId}-${turnId}`;
      setMessages((current) => {
        if (current.some((message) => message.id === localId)) return current;
        return [...current, {
          id: localId,
          conversation_id: conversationId ?? "",
          actor_id: "creator",
          role: "creator",
          content: text,
          route: "deus",
          metadata_json: { voice: true, optimistic: true },
          correlation_id: "",
          created_at: new Date().toISOString(),
        }];
      });
    },
    onTextDelta: (delta, turnId, provider, sessionId) => {
      const localId = `local-deus-voice-${sessionId}-${turnId}`;
      setMessages((current) => {
        const existing = current.find((message) => message.id === localId);
        if (!existing) {
          return [...current, {
            id: localId,
            conversation_id: conversationId ?? "",
            actor_id: "deus",
            role: "deus",
            content: delta,
            route: "deus",
            metadata_json: { voice: true, provider, streaming: true },
            correlation_id: "",
            created_at: new Date().toISOString(),
          }];
        }
        return current.map((message) => message.id === localId
          ? { ...message, content: message.content + delta, metadata_json: { ...message.metadata_json, provider } }
          : message);
      });
    },
    onReply: ({ sessionId, turnId, text, provider }) => {
      const localId = `local-deus-voice-${sessionId}-${turnId}`;
      setMessages((current) => current.map((message) => message.id === localId
        ? { ...message, content: text, metadata_json: { voice: true, provider, streaming: false } }
        : message));
    },
  });

  useEffect(() => {
    if (pending || ["committing", "thinking"].includes(voiceSession.status)) onMoodChange?.("thinking");
    else if (voiceSession.status === "speaking") onMoodChange?.("speaking");
    else if (voiceSession.status === "listening") onMoodChange?.("listening");
    else onMoodChange?.("idle");
  }, [pending, voiceSession.status, onMoodChange]);

  useEffect(() => {
    if (!enabled || conversationId || creatingConversation.current) return;
    creatingConversation.current = true;
    void createConversation()
      .then((conversation) => {
        window.localStorage.setItem(CONVERSATION_KEY, conversation.id);
        setConversationId(conversation.id);
      })
      .catch(() => setError("Não foi possível iniciar a conversa com DEUS."))
      .finally(() => { creatingConversation.current = false; });
  }, [enabled, conversationId]);

  useEffect(() => () => onMoodChange?.("idle"), [onMoodChange]);

  useEffect(() => {
    if (!conversationId) return;
    void fetchConversationMessages(conversationId)
      .then(setMessages)
      .catch(() => {
        window.localStorage.removeItem(CONVERSATION_KEY);
        setConversationId(null);
        setMessages([]);
      });
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return;
    // Proposals still waiting for the Creator survive a reload.
    void fetchInceptions()
      .then((items) => Promise.all(items
        .filter((item) => item.conversation_id === conversationId && item.trinity_assessment.verdict
          && ["awaiting_creator_decision", "approved"].includes(item.status))
        .map(loadProposal)))
      .then((loaded) => setProposals(loaded.filter((item) => proposalStage(item) !== "settled")))
      .catch(() => undefined);
  }, [conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, proposals, pending]);

  function upsertProposal(proposal: Proposal) {
    setProposals((items) => [...items.filter((item) => item.inception.id !== proposal.inception.id), proposal]);
  }

  async function act(proposal: Proposal, action: ProposalAction) {
    const { inception, mission } = proposal;
    setDeciding(inception.id);
    setError(null);
    try {
      if (action === "start" && mission) {
        upsertProposal({ inception, mission: await startMission(mission.id) });
      } else if (action === "cancel" && mission && mission.status !== "validated") {
        // A start that stopped halfway (authorized or distributed) is cancelled on the Mission itself.
        upsertProposal({ inception, mission: await cancelMission(mission.id) });
      } else if (action === "cancel") {
        upsertProposal(await loadProposal(await decideInception(inception.id, "cancel")));
      } else {
        upsertProposal({ inception: await decideInception(inception.id, "reject"), mission });
      }
    } catch {
      setError(action === "start" ? "The Mission could not start." : "The decision could not be recorded.");
    } finally {
      setDeciding(null);
    }
  }

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || !enabled || pending) return;
    setPending(true);
    setError(null);
    let optimisticId: string | null = null;
    try {
      let id = conversationId;
      if (!id) {
        const conversation = await createConversation();
        id = conversation.id;
        window.localStorage.setItem(CONVERSATION_KEY, id);
        setConversationId(id);
      }
      setInput("");

      // Render the Creator's words immediately; do not make the UI wait for inference.
      optimisticId = `local-creator-${newRequestId()}`;
      const optimistic: ConversationMessage = {
        id: optimisticId,
        conversation_id: id,
        actor_id: "creator",
        role: "creator",
        content,
        route: "deus",
        metadata_json: { optimistic: true },
        correlation_id: "",
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [...current, optimistic]);

      const reply = await converseWithDeus(id, content);
      if (!reply.response?.trim()) throw new Error("EMPTY_DEUS_RESPONSE");
      const creatorMessage: ConversationMessage = {
        ...optimistic,
        id: reply.message_id || optimistic.id,
        metadata_json: {},
        correlation_id: reply.correlation_id || "",
      };
      const deusMessage: ConversationMessage = {
        id: `local-deus-${reply.correlation_id || newRequestId()}`,
        conversation_id: id,
        actor_id: "deus",
        role: "deus",
        content: reply.response,
        route: "deus",
        metadata_json: {},
        correlation_id: reply.correlation_id || "",
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [
        ...current.filter((message) => message.id !== optimistic.id),
        creatorMessage,
        deusMessage,
      ]);
      optimisticId = null;

      if (reply.inception) {
        void fetchInception(reply.inception.id).then(loadProposal).then(upsertProposal).catch(() => undefined);
      }
    } catch (failure) {
      if (optimisticId) {
        setMessages((current) => current.filter((message) => message.id !== optimisticId));
      }
      const message = failure instanceof Error ? failure.message : "CONVERSATION_FAILED";
      setError(
        message === "AUTH_REQUIRED"
          ? "Sessão expirada. Entre novamente para continuar."
          : ["HTTP_502", "HTTP_503", "HTTP_504", "DEUS_TEMPORARILY_UNAVAILABLE"].includes(message)
            ? "DEUS está temporariamente sem resposta dos provedores de inferência. Tente novamente."
            : "Não foi possível concluir a conversa com DEUS.",
      );
    } finally {
      setPending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <section className="creator-console" aria-labelledby="creator-console-title">
      <h2 id="creator-console-title" className="sr-only">Creator Console</h2>
      <div className="console-messages" ref={scrollRef} aria-live="polite">
        {timeline(messages, proposals).map((entry) => entry.kind === "proposal" ? (
          <TrinityProposal
            key={entry.proposal.inception.id}
            proposal={entry.proposal}
            busy={deciding === entry.proposal.inception.id}
            onAct={(action) => void act(entry.proposal, action)}
          />
        ) : (
          <div className={`console-message ${entry.message.role === "deus" ? "deus-message" : "creator-message"}`} key={entry.message.id}>
            <span>{entry.message.role === "deus" ? "DEUS" : "CREATOR"}</span>
            <p>{entry.message.content}</p>
          </div>
        ))}
        {pending && <div className="console-thinking" aria-label="DEUS is thinking"><i /><i /><i /></div>}
      </div>
      <form className="console-form" noValidate onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); void send(); }}>
        <textarea
          className="resize-none"
          aria-label="Message DEUS"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={voiceSession.status === "listening" ? "Ouvindo…" : enabled ? "Fale “Deus” ou digite para conversar…" : "Configure um provedor de inferência para falar com DEUS."}
          disabled={!enabled || pending}
          rows={1}
        />
        <button type="submit" aria-label="Send to DEUS" disabled={!enabled || pending || !input.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </form>
      <div className={`wake-hint ${voiceSession.status}`} aria-live="polite">
        <i />
        {({
          disabled: "Voz em tempo real desativada",
          connecting: "Conectando a DEUS…",
          ready: "Pronto · diga “Deus”",
          listening: "Ouvindo…",
          committing: "Entendido…",
          thinking: "Pensando…",
          speaking: "DEUS está falando · interrompa naturalmente se quiser",
          reconnecting: "Reconectando…",
          error: "A conversa por voz precisa de atenção",
        } as const)[voiceSession.status]}
        {voiceSession.provider && <small> · {voiceSession.provider}</small>}
      </div>
      {(error ?? voiceSession.error) && <div className="console-error" role="alert">{error ?? voiceSession.error}</div>}
    </section>
  );
}
