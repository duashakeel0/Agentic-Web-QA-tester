import { useEffect, useMemo, useRef } from "react";
import { AlertTriangle, CheckCircle2, ListChecks, MessagesSquare, Radar, Sparkles } from "lucide-react";
import type { FeedMessage } from "../hooks/usePipelineRun";
import type { AgentName, Provider } from "../types/pipeline";
import "./TalkingAgentsPanel.css";

const AGENT_LABELS: Record<AgentName, string> = {
  planner: "Planner",
  explorer: "Explorer",
  verifier: "Verifier",
  reporter: "Reporter",
};
const AGENT_ICONS: Record<AgentName, typeof Sparkles> = {
  planner: ListChecks,
  explorer: Radar,
  verifier: CheckCircle2,
  reporter: MessagesSquare,
};
const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Ollama" };

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Derives which agent(s) are still "talking" straight from the feed that's
 * already streamed in - the last thing said for a given provider+agent pair
 * is a "start" message with no matching "end"/"error" after it yet. No new
 * data is required from the caller for this. */
function activeAgents(feed: FeedMessage[]): { provider: Provider; agent: AgentName }[] {
  const lastKindByKey = new Map<string, FeedMessage["kind"]>();
  const orderByKey = new Map<string, { provider: Provider; agent: AgentName }>();
  for (const message of feed) {
    const key = `${message.provider}:${message.agent}`;
    lastKindByKey.set(key, message.kind);
    orderByKey.set(key, { provider: message.provider, agent: message.agent });
  }
  const active: { provider: Provider; agent: AgentName }[] = [];
  for (const [key, kind] of lastKindByKey) {
    if (kind === "start") {
      const entry = orderByKey.get(key);
      if (entry) active.push(entry);
    }
  }
  return active;
}

function TalkingAgentsPanel({ feed, showProvider }: { feed: FeedMessage[]; showProvider: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const active = useMemo(() => activeAgents(feed), [feed]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [feed.length, active.length]);

  return (
    <div className="talking-agents-panel" role="log" aria-label="Live agent activity feed">
      {feed.length === 0 && active.length === 0 && (
        <div className="talking-agents-empty">
          <MessagesSquare size={22} aria-hidden="true" />
          <p>Agent activity will appear here once the run starts.</p>
        </div>
      )}
      {feed.map((message) => {
        const Icon = AGENT_ICONS[message.agent];
        return (
          <div
            className={`agent-bubble agent-bubble-${message.kind} agent-color-${message.agent}`}
            key={message.id}
          >
            <span className="agent-bubble-icon" aria-hidden="true">
              {message.kind === "error" ? <AlertTriangle size={14} /> : <Icon size={14} />}
            </span>
            <div className="agent-bubble-content">
              <div className="agent-bubble-header">
                <span className="agent-name">{AGENT_LABELS[message.agent]}</span>
                {showProvider && (
                  <span className={`agent-provider agent-provider-${message.provider}`}>
                    {PROVIDER_LABELS[message.provider]}
                  </span>
                )}
                <span className="agent-bubble-time">{formatTime(message.timestamp)}</span>
              </div>
              <p className="agent-bubble-text">{message.text}</p>
            </div>
          </div>
        );
      })}
      {active.map(({ provider, agent }) => {
        const Icon = AGENT_ICONS[agent];
        return (
          <div className={`agent-bubble agent-bubble-typing agent-color-${agent}`} key={`typing-${provider}-${agent}`}>
            <span className="agent-bubble-icon agent-bubble-icon-pulse" aria-hidden="true">
              <Icon size={14} />
            </span>
            <div className="agent-bubble-content">
              <div className="agent-bubble-header">
                <span className="agent-name">{AGENT_LABELS[agent]}</span>
                {showProvider && (
                  <span className={`agent-provider agent-provider-${provider}`}>{PROVIDER_LABELS[provider]}</span>
                )}
              </div>
              <span className="agent-typing-dots" aria-label={`${AGENT_LABELS[agent]} is working`}>
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}

export default TalkingAgentsPanel;
