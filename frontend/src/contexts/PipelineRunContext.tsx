import { createContext, useContext, type ReactNode } from "react";
import { usePipelineRun } from "../hooks/usePipelineRun";

type PipelineRunContextValue = ReturnType<typeof usePipelineRun>;

const PipelineRunContext = createContext<PipelineRunContextValue | null>(null);

/** Holds the one live pipeline run (and its WebSocket connection) above the
 * router so it survives navigation - Dashboard and RunTest both read/drive
 * the same run through this instead of each mounting their own
 * usePipelineRun(), which used to tear the connection down and lose all
 * live state the moment you clicked away to History/Compare/Analytics. */
export function PipelineRunProvider({ children }: { children: ReactNode }) {
  const run = usePipelineRun();
  return <PipelineRunContext.Provider value={run}>{children}</PipelineRunContext.Provider>;
}

export function usePipelineRunContext(): PipelineRunContextValue {
  const ctx = useContext(PipelineRunContext);
  if (ctx === null) {
    throw new Error("usePipelineRunContext must be used within a PipelineRunProvider.");
  }
  return ctx;
}
