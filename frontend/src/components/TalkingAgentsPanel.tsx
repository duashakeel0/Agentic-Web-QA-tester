import { useEffect, useRef } from "react";
import type { FeedMessage } from "../hooks/usePipelineRun";
import type { AgentName, Provider } from "../types/pipeline";
import "./TalkingAgentsPanel.css";

const AGENT_LABELS: Record<AgentName, string> = {
  planner: "Planner",
  explorer: "Explorer",
  verifier: "Verifier",
  reporter: "Reporter",
};
const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Ollama" };

function TalkingAgentsPanel({ feed, showProvider }: { feed: FeedMessage[]; showProvider: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [feed.length]);

  return (
    <div className="talking-agents-panel">
      {feed.length === 0 && <p className="talking-agents-empty">Agent activity will appear here once the run starts.</p>}
      {feed.map((message) => (
        <div className={`agent-bubble agent-bubble-${message.kind}`} key={message.id}>
          <div className="agent-bubble-header">
            <span className="agent-name">{AGENT_LABELS[message.agent]}</span>
            {showProvider && <span className={`agent-provider agent-provider-${message.provider}`}>{PROVIDER_LABELS[message.provider]}</span>}
          </div>
          <p className="agent-bubble-text">{message.text}</p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

export default TalkingAgentsPanel;
