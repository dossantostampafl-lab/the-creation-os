import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { converseWithDeus, createConversation, fetchConversationMessages } from "./api";
import type { ConversationMessage } from "./api";
import "./CreatorConsole.css";

type Props = {
  enabled: boolean;
};

const CONVERSATION_KEY = "creation_conversation_id";

export function CreatorConsole({ enabled }: Props) {
  const [conversationId, setConversationId] = useState(() => window.localStorage.getItem(CONVERSATION_KEY));
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!conversationId) return;
    void fetchConversationMessages(conversationId)
      .then(setMessages)
      .catch((failure: unknown) => {
        // Only a missing/foreign conversation invalidates the saved id; auth or network errors must keep it.
        if (failure instanceof Error && (failure.message === "HTTP_404" || failure.message === "HTTP_422")) {
          window.localStorage.removeItem(CONVERSATION_KEY);
          setConversationId(null);
          setMessages([]);
        }
      });
  }, [conversationId]);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = input.trim();
    if (!content || !enabled || pending) return;
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
      await converseWithDeus(id, content);
      setInput("");
      setMessages(await fetchConversationMessages(id));
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "CONVERSATION_FAILED";
      setError(
        message === "HTTP_503" ? "Inference provider is not configured."
          : message === "AUTH_REQUIRED" ? "Session expired. Sign in again."
          : message === "HTTP_429" ? "Too many requests. Try again shortly."
          : "DEUS conversation failed. Your message was kept.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <article className="panel creator-console">
      <div className="panel-title">CREATOR CONSOLE</div>
      <div className="console-heading">
        <div><span className="eyebrow">DIRECT INTERFACE</span><h2>Creator Console</h2></div>
        <span className={`pill ${enabled ? "good" : "warn"}`}>{enabled ? "DEUS READY" : "INFERENCE REQUIRED"}</span>
      </div>
      <div className="console-messages" aria-live="polite">
        {messages.length ? messages.map((message) => (
          <div className={`console-message ${message.role === "deus" ? "deus-message" : "creator-message"}`} key={message.id}>
            <span>{message.role === "deus" ? "DEUS" : "CREATOR"}</span>
            <p>{message.content}</p>
          </div>
        )) : <div className="empty">No conversation yet.</div>}
      </div>
      <form className="console-form" onSubmit={send}>
        <textarea
          aria-label="Message DEUS"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={enabled ? "Speak to DEUS…" : "Configure an inference provider to speak to DEUS."}
          disabled={!enabled || pending}
          rows={2}
        />
        <button type="submit" disabled={!enabled || pending || !input.trim()}>{pending ? "Sending…" : "Send to DEUS"}</button>
      </form>
      {error && <div className="console-error">{error}</div>}
    </article>
  );
}
