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
  if (status === "done") return <span className="stage-icon stage-done">✔</span>;
  if (status === "error") return <span className="stage-icon stage-error">✕</span>;
  if (status === "running") return <span className="stage-icon stage-running">⏳</span>;
  return <span className="stage-icon stage-pending">○</span>;
}

function PipelineTimeline({ stages }: { stages: Partial<Record<Provider, StageMap>> }) {
  const providers = Object.keys(stages) as Provider[];

  return (
    <div className="pipeline-timeline">
      {providers.map((provider) => (
        <div className="timeline-column" key={provider}>
          {providers.length > 1 && <span className="timeline-provider">{PROVIDER_LABELS[provider]}</span>}
          <div className="timeline-steps">
            {AGENTS.map((agent) => {
              const stage = stages[provider]?.[agent] ?? { status: "pending" as const };
              return (
                <div className={`timeline-step timeline-${stage.status}`} key={agent}>
                  <StageIcon status={stage.status} />
                  <span className="timeline-step-label">{AGENT_LABELS[agent]}</span>
                  {stage.durationMs !== undefined && (
                    <span className="timeline-step-duration">{(stage.durationMs / 1000).toFixed(1)}s</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default PipelineTimeline;
