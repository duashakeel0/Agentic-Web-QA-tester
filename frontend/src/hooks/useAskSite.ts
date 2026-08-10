import { useCallback, useRef, useState } from "react";
import { getAskSiteSocketUrl } from "../services/api";
import type { AskSiteContext, AskSiteEvent } from "../types/asksite";
import type { Provider } from "../types/pipeline";

export type AskSiteStatus = "idle" | "connecting" | "thinking" | "answered" | "declined" | "error";

export interface AskSiteState {
  status: AskSiteStatus;
  question: string | null;
  domain: string | null;
  answer: string | null;
  source: "existing_context" | "live_explore" | null;
  reason: string | null; // set when declined
  liveStep: string | null; // e.g. "click on #menu" - a lightweight "still browsing" indicator
  errorMessage: string | null;
}

const IDLE_STATE: AskSiteState = {
  status: "idle", question: null, domain: null, answer: null, source: null,
  reason: null, liveStep: null, errorMessage: null,
};

/** Drives one on-demand "Ask the Site" question at a time over
 * /ws/ask-site - a fresh WebSocket per question, closed once the
 * terminal event (declined/answer/error) arrives, same one-shot-request
 * shape as the question itself. */
export function useAskSite() {
  const [state, setState] = useState<AskSiteState>(IDLE_STATE);
  const socketRef = useRef<WebSocket | null>(null);

  const reset = useCallback(() => {
    socketRef.current?.close();
    setState(IDLE_STATE);
  }, []);

  const ask = useCallback((question: string, provider: Provider, context: AskSiteContext | null) => {
    socketRef.current?.close();
    setState({ ...IDLE_STATE, status: "connecting", question });

    const socket = new WebSocket(getAskSiteSocketUrl());
    socketRef.current = socket;

    socket.onopen = () => {
      setState((prev) => ({ ...prev, status: "thinking" }));
      socket.send(JSON.stringify({ question, provider, context }));
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as AskSiteEvent;

      if (data.type === "status") {
        setState((prev) => ({ ...prev, status: "thinking" }));
      } else if (data.type === "action") {
        setState((prev) => ({ ...prev, status: "thinking", liveStep: `${data.action} on ${data.selector ?? "the page"}` }));
      } else if (data.type === "declined") {
        setState((prev) => ({ ...prev, status: "declined", reason: data.reason }));
        socket.close();
      } else if (data.type === "answer") {
        setState((prev) => ({
          ...prev, status: "answered", domain: data.domain, answer: data.answer, source: data.source,
        }));
        socket.close();
      } else if (data.type === "error") {
        setState((prev) => ({ ...prev, status: "error", errorMessage: data.message }));
        socket.close();
      }
    };

    socket.onerror = () => {
      setState((prev) => ({ ...prev, status: "error", errorMessage: "Could not connect to the backend WebSocket." }));
    };
  }, []);

  return { ...state, ask, reset };
}
