import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Loader2, Search, X } from "lucide-react";
import { apiGet } from "../services/api";
import { useAskSite } from "../hooks/useAskSite";
import { usePipelineRunContext } from "../contexts/PipelineRunContext";
import type { AskSiteContext } from "../types/asksite";
import type { Provider } from "../types/pipeline";
import "./AskSiteBar.css";

interface DomainSummary {
  name: string;
  base_url: string;
}

function stripSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

/** Day 10's "Ask the Site" search bar - available on the dashboard at all
 * times (mounted once in DashboardLayout's topbar, independent of route
 * or whether a test is running). Reuses the Explorer in on-demand mode
 * through /ws/ask-site rather than a separate agent; when a run is
 * active or just finished for a matching domain, its already-collected
 * context (final page text, or - mid-run - the actions observed so far)
 * is sent along so the backend answers from that instead of
 * re-exploring the site from scratch. */
function AskSiteBar() {
  const [question, setQuestion] = useState("");
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const { status, domain, answer, source, reason, liveStep, errorMessage, ask, reset } = useAskSite();
  const run = usePipelineRunContext();

  useEffect(() => {
    apiGet<DomainSummary[]>("/api/domains")
      .then(setDomains)
      .catch(() => {
        // Best-effort - just means the mid-run "richer context" path
        // below can't resolve a base_url to a domain name yet; the
        // question still works, it just always does a live check.
      });
  }, []);

  const activeProvider = useMemo<Provider | null>(() => {
    const providers: Provider[] = ["claude", "ollama"];
    return providers.find((p) => run.results[p] || run.baseUrls[p]) ?? null;
  }, [run.results, run.baseUrls]);

  function buildContext(): AskSiteContext | null {
    if (!activeProvider) return null;

    // After a run: the richest context available - the Explorer's real
    // final page state, not just the actions along the way.
    const finished = run.results[activeProvider];
    if (finished?.exploration && finished.plan.domain) {
      return {
        domain: finished.plan.domain,
        final_url: finished.exploration.final_url,
        final_page_text: finished.exploration.final_page_text,
        actions: finished.exploration.actions.map((a) => ({
          step: a.step, action: a.action, selector: a.selector, value: a.value, success: a.success, error: a.error,
        })),
      };
    }

    // During a run: no final page state yet, but every real action
    // observed so far is still "richer context already collected" -
    // resolved to a real registered domain via the base_url the
    // Explorer's first "page_loaded" action reported.
    const baseUrl = run.baseUrls[activeProvider];
    if (baseUrl) {
      const matched = domains.find((d) => stripSlash(d.base_url) === stripSlash(baseUrl));
      if (matched) {
        const actions = run.actionsLog[activeProvider] ?? [];
        return {
          domain: matched.name,
          final_url: null,
          final_page_text: null,
          actions: actions.map((a) => ({
            step: a.step, action: a.action, selector: a.selector, value: a.value, success: a.success, error: a.error,
          })),
        };
      }
    }

    return null;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    ask(trimmed, "claude", buildContext());
  }

  const isOpen = status !== "idle";
  const isBusy = status === "connecting" || status === "thinking";

  return (
    <div className="ask-site-bar">
      <form className="ask-site-form" onSubmit={handleSubmit} role="search">
        <Search size={15} className="ask-site-icon" aria-hidden="true" />
        <input
          type="text"
          placeholder="Ask about a site… e.g. “What categories does ParaBank have?”"
          aria-label="Ask about a site"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        {isBusy && <Loader2 size={15} className="ask-site-spinner spin" aria-hidden="true" />}
      </form>

      {isOpen && (
        <div className="ask-site-panel">
          <button type="button" className="ask-site-close" onClick={reset} aria-label="Close">
            <X size={13} />
          </button>

          {isBusy && <p className="ask-site-status">{liveStep ? `Browsing… ${liveStep}` : "Thinking…"}</p>}

          {status === "declined" && (
            <p className="ask-site-declined">
              No domain knowledge for this{reason ? ` - ${reason}` : "."}
            </p>
          )}

          {status === "answered" && (
            <div className="ask-site-answer">
              <div className="ask-site-answer-meta">
                <span className="ask-site-domain-badge">{domain}</span>
                <span className="ask-site-source">
                  {source === "existing_context" ? "from the current run" : "from a live check just now"}
                </span>
              </div>
              <p>{answer}</p>
            </div>
          )}

          {status === "error" && <p className="ask-site-declined">{errorMessage}</p>}
        </div>
      )}
    </div>
  );
}

export default AskSiteBar;
