import { useState, type FormEvent } from "react";
import { apiPost, ApiError } from "../services/api";
import "./AskAboutTest.css";

interface QaMessage {
  question: string;
  answer: string;
}

const SUGGESTIONS = ["Why did this fail?", "What are the critical issues?", "How confident is this result?"];

function AskAboutTest({ runId }: { runId: number }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<QaMessage[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(text: string) {
    if (!text.trim() || asking) return;
    setAsking(true);
    setError(null);
    try {
      const response = await apiPost<{ answer: string }>(`/api/history/${runId}/ask`, { question: text });
      setMessages((prev) => [...prev, { question: text, answer: response.answer }]);
      setQuestion("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not get an answer right now.");
    } finally {
      setAsking(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    ask(question);
  }

  return (
    <div className="ask-about-test">
      <h3 className="ask-title">Ask about this test</h3>

      {messages.length === 0 && !asking && (
        <div className="ask-suggestions">
          {SUGGESTIONS.map((s) => (
            <button type="button" key={s} onClick={() => ask(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      {messages.length > 0 && (
        <div className="ask-messages">
          {messages.map((m, i) => (
            <div className="ask-message" key={i}>
              <p className="ask-question">{m.question}</p>
              <p className="ask-answer">{m.answer}</p>
            </div>
          ))}
        </div>
      )}

      {error && <p className="ask-error">{error}</p>}

      <form className="ask-form" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Type your question…"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={asking}
        />
        <button type="submit" disabled={asking || !question.trim()}>
          {asking ? "…" : "→"}
        </button>
      </form>
    </div>
  );
}

export default AskAboutTest;
