import { useEffect, useRef, useState, type FormEvent } from "react";
import { MessageCircle, Send, X } from "lucide-react";
import { apiPost, ApiError } from "../services/api";
import "./GlobalChat.css";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** A general-purpose assistant, reachable from every page in the dashboard -
 * unlike AskAboutTest, this isn't grounded in any one report; it answers
 * whatever it's asked. */
function GlobalChat() {
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
      const response = await apiPost<{ reply: string }>("/api/chat", {
        message: text,
        history: messages,
      });
      setMessages([...nextMessages, { role: "assistant", content: response.reply }]);
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
            <span className="global-chat-subtitle">Not limited to test reports - ask about anything.</span>
          </div>

          <div className="global-chat-messages">
            {messages.length === 0 && (
              <p className="global-chat-empty">Ask about a new workflow idea, how something works, or anything else.</p>
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
