import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { AgentName, Provider } from "../types/pipeline";
import type { StageMap } from "../hooks/usePipelineRun";
import "./PipelineTimeline.css";

const AGENT_LABELS: Record<AgentName, string> = {
  planner: "Planner",
  explorer: "Explorer",
  verifier: "Verifier",
  reporter: "Reporter",
};
const AGENTS: AgentName[] = ["planner", "explorer", "verifier", "reporter"];

const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Llama (Ollama)" };

function StageIcon({ status }: { status: StageMap[AgentName]["status"] }) {
  if (status === "done") return <CheckCircle2 size={18} className="stage-icon stage-done" aria-hidden="true" />;
  if (status === "error") return <XCircle size={18} className="stage-icon stage-error" aria-hidden="true" />;
  if (status === "running") return <Loader2 size={18} className="stage-icon stage-running" aria-hidden="true" />;
  return <Circle size={18} className="stage-icon stage-pending" aria-hidden="true" />;
}

/** Ticks once a second so a running stage's elapsed time visibly counts up
 * instead of sitting static - the difference between "still working" and
 * "frozen" is otherwise invisible once the initial message has scrolled by. */
function useNow(enabled: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [enabled]);
  return now;
}

function PipelineTimeline({ stages }: { stages: Partial<Record<Provider, StageMap>> }) {
  const providers = Object.keys(stages) as Provider[];
  const anyRunning = providers.some((p) => Object.values(stages[p] ?? {}).some((s) => s.status === "running"));
  const now = useNow(anyRunning);

  return (
    <div className="pipeline-timeline">
      {providers.map((provider) => (
        <div className="timeline-column" key={provider}>
          {providers.length > 1 && (
            <span className={`timeline-provider timeline-provider-${provider}`}>{PROVIDER_LABELS[provider]}</span>
          )}
          <ol className="timeline-steps">
            {AGENTS.map((agent, index) => {
              const stage = stages[provider]?.[agent] ?? { status: "pending" as const };
              const elapsedSeconds =
                stage.status === "running" && stage.startedAt ? Math.max(0, Math.round((now - stage.startedAt) / 1000)) : null;
              return (
                <li className={`timeline-step timeline-${stage.status}`} key={agent}>
                  <span className="timeline-step-rail" aria-hidden="true">
                    <StageIcon status={stage.status} />
                    {index < AGENTS.length - 1 && <span className="timeline-connector" />}
                  </span>
                  <span className="timeline-step-body">
                    <span className="timeline-step-label">{AGENT_LABELS[agent]}</span>
                    {stage.durationMs !== undefined && (
                      <span className="timeline-step-duration">{(stage.durationMs / 1000).toFixed(1)}s</span>
                    )}
                    {elapsedSeconds !== null && (
                      <span className="timeline-step-duration timeline-step-elapsed">
                        {elapsedSeconds}s{elapsedSeconds > 30 ? " — still working" : ""}
                      </span>
                    )}
                    {stage.status === "error" && stage.message && (
                      <span className="timeline-step-duration timeline-step-error-msg">{stage.message}</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </div>
  );
}

export default PipelineTimeline;
