import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import {
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
import { spokenDecision, useDeusEars, useDeusVoice, voiceText } from "./voice";
import type { SpokenDecision } from "./voice";
import "./CreatorConsole.css";

type Props = {
  enabled: boolean;
  onMoodChange?: (mood: CosmosMood) => void;
};

const CONVERSATION_KEY = "creation_conversation_id";

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

/** What a spoken answer means for a proposal at its current stage; null lets DEUS hear it instead. */
function spokenAction(proposal: Proposal, decision: SpokenDecision): ProposalAction | null {
  const stage = proposalStage(proposal);
  if (stage === "ready") return decision === "authorize" || decision === "approve" ? "start" : "cancel";
  if (stage === "blocked" && (decision === "cancel" || decision === "reject")) return "dismiss";
  return null;
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
  // Text the ears put in the box; only that text may be replaced or cleared by them.
  const voiceDraft = useRef("");
  // A voice conversation: after each spoken reply DEUS listens again without the wake word,
  // until the Creator goes quiet, says goodbye, or starts typing.
  const [inConversation, setInConversation] = useState(false);
  const conversing = useRef(false);
  const setConversing = (value: boolean) => {
    conversing.current = value;
    setInConversation(value);
  };
  const voice = useDeusVoice();
  const ears = useDeusEars({
    // Never listen while DEUS cannot answer, is thinking, or is speaking (it would hear itself).
    paused: !enabled || pending || voice.speaking,
    onWake: () => {
      setConversing(true);
      voice.speak(voiceText.greeting());
    },
    onCommand: (text) => {
      setConversing(true);
      const decision = spokenDecision(text);
      // A spoken answer is about the proposal DEUS presented last.
      const latest = proposals
        .filter((item) => proposalStage(item) !== "settled")
        .sort((a, b) => Date.parse(a.inception.proposed_at) - Date.parse(b.inception.proposed_at))
        .at(-1);
      const action = decision && latest ? spokenAction(latest, decision) : null;
      if (action && latest) {
        setInput("");
        void act(latest, action, true);
        return;
      }
      setInput(text);
      void send(text);
    },
    onLapse: () => setConversing(false),
    onFarewell: () => {
      setConversing(false);
      voice.speak(voiceText.farewell());
    },
    onInterim: (text) => {
      setInput((typed) => (typed === voiceDraft.current || typed === "" ? text : typed));
      voiceDraft.current = text;
    },
  });

  useEffect(() => {
    if (pending) onMoodChange?.("thinking");
    else if (voice.speaking) onMoodChange?.("speaking");
    else if (ears.state === "attentive") onMoodChange?.("listening");
    else onMoodChange?.("idle");
  }, [pending, voice.speaking, ears.state, onMoodChange]);

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

  async function act(proposal: Proposal, action: ProposalAction, spoken = false) {
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
      if (spoken) {
        const confirmation = { start: voiceText.started, cancel: voiceText.cancelled, dismiss: voiceText.dismissed }[action];
        voice.speak(confirmation(), { onEnd: () => { if (conversing.current) ears.summon(); } });
      }
    } catch {
      setError(action === "start" ? "The Mission could not start." : "The decision could not be recorded.");
      // No confirmation will be spoken, so nothing would reopen the ears.
      if (spoken) setConversing(false);
    } finally {
      setDeciding(null);
    }
  }

  function voiceReply(latest: ConversationMessage[]) {
    const reply = [...latest].reverse().find((message) => message.role === "deus");
    if (!reply) return;
    // Keep the conversation going: listen for the follow-up once DEUS has finished speaking.
    voice.speak(reply.content, { onEnd: () => { if (conversing.current) ears.summon(); } });
  }

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || !enabled || pending) return;
    voice.stop();
    setPending(true);
    setError(null);
    try {
      let id = conversationId;
      if (!id) {
        const conversation = await createConversation();
        id = conversation.id;
        window.localStorage.setItem(CONVERSATION_KEY, id);
        setConversationId(id);
      }
      setInput("");
      const reply = await converseWithDeus(id, content);
      const latest = await fetchConversationMessages(id);
      setMessages(latest);
      if (reply.inception) {
        await fetchInception(reply.inception.id).then(loadProposal).then(upsertProposal).catch(() => undefined);
      }
      voiceReply(latest);
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "CONVERSATION_FAILED";
      setError(message === "HTTP_503" ? "Inference provider is not configured." : "DEUS conversation failed.");
      setConversing(false);
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
          onChange={(event) => {
            // Typing takes over from listening.
            if (ears.state === "attentive") ears.dismiss();
            setConversing(false);
            setInput(event.target.value);
          }}
          onKeyDown={handleKeyDown}
          placeholder={ears.state === "attentive" ? voiceText.listening() : enabled ? "Speak to DEUS…" : "Configure an inference provider to speak to DEUS."}
          disabled={!enabled || pending}
          rows={1}
        />
        {voice.supported && (
          <button
            type="button"
            className={`icon-button${voice.enabled ? " active" : ""}`}
            aria-label={voice.enabled ? "Mute DEUS voice" : "Unmute DEUS voice"}
            aria-pressed={voice.enabled}
            onClick={voice.toggle}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 9h4l5-4v14l-5-4H4z" />
              {voice.enabled ? <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" /> : <path d="M16 9l5 6M21 9l-5 6" />}
            </svg>
          </button>
        )}
        {ears.supported && (
          <>
            <button
              type="button"
              className={`icon-button wake${ears.wakeEnabled ? " active" : ""}`}
              aria-label={ears.wakeEnabled ? "Turn off “Deus” wake word" : "Turn on “Deus” wake word"}
              aria-pressed={ears.wakeEnabled}
              disabled={!enabled}
              onClick={ears.toggleWake}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10a5 5 0 0 1 10 0c0 3-2 3.5-2.5 6a3 3 0 0 1-5.5 1.5M9.5 10a2.5 2.5 0 0 1 5 0" /></svg>
            </button>
            <button
              type="button"
              className={`icon-button mic${ears.state === "attentive" ? " live" : ""}`}
              aria-label={ears.state === "attentive" ? "Stop listening" : "Talk to DEUS"}
              aria-pressed={ears.state === "attentive"}
              disabled={!enabled || pending}
              onClick={ears.state === "attentive" ? () => { setConversing(false); ears.dismiss(); } : () => { voice.stop(); setConversing(true); ears.summon(); }}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
            </button>
          </>
        )}
        <button type="submit" aria-label="Send to DEUS" disabled={!enabled || pending || !input.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </form>
      {inConversation
        ? <div className="wake-hint conversing" aria-live="polite"><i />{voiceText.conversationHint()}</div>
        : ears.state === "sleeping" && <div className="wake-hint" aria-live="polite"><i />{voiceText.wakeHint()}</div>}
      {(error ?? ears.error) && <div className="console-error" role="alert">{error ?? ears.error}</div>}
    </section>
  );
}
