import { useCallback, useRef, useState } from "react";
import { getPipelineSocketUrl } from "../services/api";
import type {
  AgentName,
  ComparisonReport,
  ModelChoice,
  PipelineEvent,
  PipelineResult,
  Provider,
  TargetBox,
  Viewport,
} from "../types/pipeline";

const AGENTS: AgentName[] = ["planner", "explorer", "verifier", "reporter"];

export type StageStatus = "pending" | "running" | "done" | "error";

export interface StageState {
  status: StageStatus;
  message?: string;
  durationMs?: number;
  startedAt?: number; // Date.now() when this stage started - lets the UI
  // show a live elapsed-time tick for a running stage instead of a static
  // spinner, so a genuinely slow (not frozen) call still reads as "working".
}

export type StageMap = Record<AgentName, StageState>;

export interface FeedMessage {
  id: string;
  provider: Provider;
  agent: AgentName;
  kind: "start" | "end" | "error";
  text: string;
  timestamp: number;
}

export type RunStatus = "idle" | "connecting" | "running" | "done" | "error";

export interface ActionFrame {
  step: string;
  action: string;
  selector: string | null;
  value: string | null;
  success: boolean;
  error: string | null;
  screenshotUrl: string | null;
  targetBox: TargetBox | null;
  viewport: Viewport | null;
  timestamp: number;
  isBrokenInputAttempt: boolean;
}

// Bounds how many recent frames a filmstrip keeps per provider - a live
// view, not a full recording, so only the tail end matters.
const MAX_FRAME_HISTORY = 10;

function freshStageMap(): StageMap {
  return {
    planner: { status: "pending" },
    explorer: { status: "pending" },
    verifier: { status: "pending" },
    reporter: { status: "pending" },
  };
}

const AGENT_VERB: Record<AgentName, string> = {
  planner: "Generating the test plan",
  explorer: "Exploring the workflow in the browser",
  verifier: "Verifying the result",
  reporter: "Generating the final report",
};

export function usePipelineRun() {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [feed, setFeed] = useState<FeedMessage[]>([]);
  const [stages, setStages] = useState<Partial<Record<Provider, StageMap>>>({});
  const [frames, setFrames] = useState<Partial<Record<Provider, ActionFrame>>>({});
  const [frameHistory, setFrameHistory] = useState<Partial<Record<Provider, ActionFrame[]>>>({});
  const [results, setResults] = useState<Partial<Record<Provider, PipelineResult>>>({});
  const [historyIds, setHistoryIds] = useState<Partial<Record<Provider, number>>>({});
  const [comparison, setComparison] = useState<ComparisonReport | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const feedIdRef = useRef(0);

  const reset = useCallback(() => {
    socketRef.current?.close();
    setStatus("idle");
    setFeed([]);
    setStages({});
    setFrames({});
    setFrameHistory({});
    setResults({});
    setHistoryIds({});
    setComparison(null);
    setErrorMessage(null);
  }, []);

  const pushFeedMessage = useCallback((provider: Provider, agent: AgentName, kind: FeedMessage["kind"], text: string) => {
    feedIdRef.current += 1;
    setFeed((prev) => [...prev, { id: `${feedIdRef.current}`, provider, agent, kind, text, timestamp: Date.now() }]);
  }, []);

  const start = useCallback(
    (ticketId: string, model: ModelChoice) => {
      setStatus("connecting");
      setFeed([]);
      setFrames({});
      setFrameHistory({});
      setResults({});
      setHistoryIds({});
      setComparison(null);
      setErrorMessage(null);

      const providers: Provider[] = model === "both" ? ["claude", "ollama"] : [model];
      setStages(Object.fromEntries(providers.map((p) => [p, freshStageMap()])) as Partial<Record<Provider, StageMap>>);

      const socket = new WebSocket(getPipelineSocketUrl());
      socketRef.current = socket;

      socket.onopen = () => {
        setStatus("running");
        socket.send(JSON.stringify({ ticket_id: ticketId, model }));
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data) as PipelineEvent;

        if (data.type === "stage_start") {
          setStages((prev) => ({
            ...prev,
            [data.provider]: {
              ...(prev[data.provider] ?? freshStageMap()),
              [data.agent]: { status: "running", startedAt: Date.now() },
            },
          }));
          pushFeedMessage(data.provider, data.agent, "start", `${AGENT_VERB[data.agent]}…`);
        } else if (data.type === "stage_end") {
          setStages((prev) => ({
            ...prev,
            [data.provider]: {
              ...(prev[data.provider] ?? freshStageMap()),
              [data.agent]: { status: "done", message: data.message, durationMs: data.duration_ms },
            },
          }));
          pushFeedMessage(data.provider, data.agent, "end", data.message);
        } else if (data.type === "stage_error") {
          setStages((prev) => ({
            ...prev,
            [data.provider]: {
              ...(prev[data.provider] ?? freshStageMap()),
              [data.agent]: { status: "error", message: data.message },
            },
          }));
          pushFeedMessage(data.provider, data.agent, "error", data.message);
        } else if (data.type === "action") {
          const frame: ActionFrame = {
            step: data.step,
            action: data.action,
            selector: data.selector,
            value: data.value,
            success: data.success,
            error: data.error,
            screenshotUrl: data.screenshot_url,
            targetBox: data.target_box,
            viewport: data.viewport,
            timestamp: Date.now(),
            isBrokenInputAttempt: data.is_broken_input_attempt,
          };
          setFrames((prev) => ({ ...prev, [data.provider]: frame }));
          setFrameHistory((prev) => {
            const existing = prev[data.provider] ?? [];
            return { ...prev, [data.provider]: [...existing, frame].slice(-MAX_FRAME_HISTORY) };
          });
        } else if (data.type === "frame") {
          // A background live-view tick, not a discrete action - swaps in
          // the newer screenshot so the picture keeps updating like a live
          // camera between actions, but never touches the filmstrip/action
          // history (that's action events only) and keeps whatever
          // step/selector/box caption the last real action set.
          setFrames((prev) => {
            const existing = prev[data.provider];
            const next: ActionFrame = existing
              ? { ...existing, screenshotUrl: data.screenshot_url, viewport: data.viewport ?? existing.viewport, timestamp: Date.now() }
              : {
                  step: "",
                  action: "live",
                  selector: null,
                  value: null,
                  success: true,
                  error: null,
                  screenshotUrl: data.screenshot_url,
                  targetBox: null,
                  viewport: data.viewport,
                  timestamp: Date.now(),
                  isBrokenInputAttempt: false,
                };
            return { ...prev, [data.provider]: next };
          });
        } else if (data.type === "pipeline_done") {
          setResults((prev) => ({ ...prev, [data.provider]: data.result }));
          setHistoryIds((prev) => ({ ...prev, [data.provider]: data.history_id }));
        } else if (data.type === "comparison_done") {
          setComparison(data.comparison);
          setStatus("done");
        } else if (data.type === "error") {
          setErrorMessage(data.message);
          setStatus("error");
        }
      };

      socket.onclose = () => {
        setStatus((prev) => (prev === "running" || prev === "connecting" ? "done" : prev));
      };

      socket.onerror = () => {
        setErrorMessage("Could not connect to the backend WebSocket.");
        setStatus("error");
      };
    },
    [pushFeedMessage],
  );

  return {
    status, feed, stages, frames, frameHistory, results, historyIds, comparison,
    errorMessage, start, reset, AGENTS,
  };
}
