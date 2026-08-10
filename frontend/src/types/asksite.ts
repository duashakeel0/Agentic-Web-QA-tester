import type { Provider } from "./pipeline";

/** Whatever richer context the dashboard already has for a live/just-
 * finished run - sent along with a question so the backend answers from
 * it directly instead of the Explorer re-exploring the same site from
 * scratch (Day 10's "during/after a run" acceptance criterion). */
export interface AskSiteContext {
  domain: string;
  final_url: string | null;
  final_page_text: string | null;
  actions: Array<{
    step: string;
    action: string;
    selector: string | null;
    value: string | null;
    success: boolean;
    error: string | null;
  }>;
}

export interface AskSiteRequest {
  question: string;
  provider: Provider;
  context: AskSiteContext | null;
}

export type AskSiteEvent =
  | { type: "status"; message: string }
  | {
      type: "action";
      step: string;
      action: string;
      selector: string | null;
      value: string | null;
      success: boolean;
      error: string | null;
      screenshot_url: string | null;
    }
  | { type: "declined"; reason: string | null }
  | { type: "answer"; domain: string; answer: string; source: "existing_context" | "live_explore"; final_url: string | null }
  | { type: "error"; message: string };
