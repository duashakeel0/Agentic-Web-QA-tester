import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { MessageCircle, Send, X } from "lucide-react";
import { usePipelineRunContext } from "../contexts/PipelineRunContext";
import { apiPost, ApiError } from "../services/api";
import type { ModelChoice } from "../types/pipeline";
import "./GlobalChat.css";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatApiResponse {
  reply: string;
  action: "run_ticket" | null;
  ticket_id: string | null;
  model: ModelChoice | null;
}

/** A general-purpose assistant, reachable from every page in the dashboard -
 * unlike AskAboutTest, this isn't grounded in any one report; it answers
 * whatever it's asked, AND can start a real ticket run when told to in
 * plain language ("run ticket ABC123") by driving the same shared pipeline
 * run a manual "New Test" submit would. */
function GlobalChat() {
  const navigate = useNavigate();
  const { start } = usePipelineRunContext();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, open]);

  async function send(text: string) {
    if (!text.trim() || sending) return;
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const response = await apiPost<ChatApiResponse>("/api/chat", {
        message: text,
        history: messages,
      });
      setMessages([...nextMessages, { role: "assistant", content: response.reply }]);
      if (response.action === "run_ticket" && response.ticket_id) {
        start(response.ticket_id, response.model ?? "claude");
        navigate("/");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the assistant right now.");
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    send(input);
  }

  return (
    <>
      <button
        type="button"
        className="global-chat-fab"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close assistant" : "Open assistant"}
        title="Ask anything"
      >
        {open ? <X size={20} aria-hidden="true" /> : <MessageCircle size={20} aria-hidden="true" />}
      </button>

      {open && (
        <div className="global-chat-panel">
          <div className="global-chat-header">
            <span>Ask anything</span>
            <span className="global-chat-subtitle">
              Ask about anything, or say "run ticket ABC123" to start a test.
            </span>
          </div>

          <div className="global-chat-messages">
            {messages.length === 0 && (
              <p className="global-chat-empty">
                Ask how ProTester works, a new workflow idea, or say "run ticket ABC123" to start a test.
              </p>
            )}
            {messages.map((m, i) => (
              <div className={`global-chat-message global-chat-${m.role}`} key={i}>
                {m.content}
              </div>
            ))}
            {sending && <div className="global-chat-message global-chat-assistant global-chat-thinking">…</div>}
            <div ref={bottomRef} />
          </div>

          {error && <p className="global-chat-error">{error}</p>}

          <form className="global-chat-form" onSubmit={handleSubmit}>
            <input
              type="text"
              placeholder="Type a message…"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              disabled={sending}
              autoFocus
            />
            <button type="submit" disabled={sending || !input.trim()} aria-label="Send message">
              <Send size={15} aria-hidden="true" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}

export default GlobalChat;
