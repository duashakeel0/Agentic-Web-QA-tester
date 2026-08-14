import { useEffect, useState, type FormEvent } from "react";
import { Globe, Plus, Trash2 } from "lucide-react";
import { apiGet, apiPost, ApiError } from "../services/api";
import "./DomainKnowledge.css";

interface Workflow {
  name: string;
  steps: string[];
  expected_outcome: { url_contains: string | null; text_contains: string | null };
}

interface Domain {
  name: string;
  base_url: string;
  workflows: Workflow[];
}

function slugPreview(raw: string): string {
  return raw.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "domain";
}

function DomainKnowledge() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [domainName, setDomainName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [workflowName, setWorkflowName] = useState("");
  const [steps, setSteps] = useState<string[]>([""]);
  const [urlContains, setUrlContains] = useState("");
  const [textContains, setTextContains] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function load() {
    setLoading(true);
    apiGet<Domain[]>("/api/domains")
      .then((data) => {
        setDomains(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load domain knowledge."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const isExistingDomain = domains.some((d) => d.name === slugPreview(domainName));

  function updateStep(index: number, value: string) {
    setSteps((prev) => prev.map((s, i) => (i === index ? value : s)));
  }
  function addStep() {
    setSteps((prev) => [...prev, ""]);
  }
  function removeStep(index: number) {
    setSteps((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    if (!domainName.trim() || !workflowName.trim()) {
      setFormError("Domain name and workflow name are required.");
      return;
    }
    if (!urlContains.trim() && !textContains.trim()) {
      setFormError("Provide at least one of URL contains / text contains - otherwise nothing can ever verify this workflow.");
      return;
    }
    const cleanSteps = steps.map((s) => s.trim()).filter(Boolean);
    if (cleanSteps.length === 0) {
      setFormError("At least one step is required.");
      return;
    }
    if (!isExistingDomain && !baseUrl.trim()) {
      setFormError('"' + domainName.trim() + '" isn\'t registered yet - a base URL is required for a new domain.');
      return;
    }

    setSubmitting(true);
    try {
      const domain = await apiPost<Domain>("/api/domains", {
        domain: domainName.trim(),
        base_url: baseUrl.trim(),
        workflow: {
          name: workflowName.trim(),
          steps: cleanSteps,
          url_contains: urlContains.trim() || null,
          text_contains: textContains.trim() || null,
        },
      });
      const saved = domain.workflows.find((w) => w.name === slugPreview(workflowName)) ?? domain.workflows.at(-1);
      setSuccessMessage(
        `Saved "${saved?.name}" to ${domain.name} - a ticket can reference it right away, no restart needed.`,
      );
      setDomainName("");
      setBaseUrl("");
      setWorkflowName("");
      setSteps([""]);
      setUrlContains("");
      setTextContains("");
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not save this workflow.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="domain-knowledge-page">
      <h1 className="domain-knowledge-title">Domain Knowledge</h1>
      <p className="domain-knowledge-subtitle">
        Every site and workflow the agents can test against. When a ticket comes back "no domain knowledge for this
        target," add it here instead of hand-editing a YAML file - it's usable by a ticket immediately.
      </p>

      <div className="domain-knowledge-layout">
        <section className="domain-knowledge-panel">
          <h2 className="domain-knowledge-panel-title">Add a workflow</h2>
          <form className="domain-knowledge-form" onSubmit={handleSubmit}>
            <label className="dk-field">
              <span>Domain name</span>
              <input
                type="text"
                value={domainName}
                onChange={(event) => setDomainName(event.target.value)}
                placeholder="e.g. parabank, or a brand-new site name"
                list="existing-domain-names"
              />
              <datalist id="existing-domain-names">
                {domains.map((d) => (
                  <option value={d.name} key={d.name} />
                ))}
              </datalist>
              {domainName.trim() && (
                <span className="dk-hint">
                  {isExistingDomain
                    ? `Adding to the existing "${slugPreview(domainName)}" domain.`
                    : `Will register a new domain named "${slugPreview(domainName)}".`}
                </span>
              )}
            </label>

            {!isExistingDomain && (
              <label className="dk-field">
                <span>Base URL (new domain only)</span>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder="https://example.com"
                />
              </label>
            )}

            <label className="dk-field">
              <span>Workflow name</span>
              <input
                type="text"
                value={workflowName}
                onChange={(event) => setWorkflowName(event.target.value)}
                placeholder="e.g. request_loan"
              />
            </label>

            <div className="dk-field">
              <span>Steps - the flow a human tester would follow, in order</span>
              {steps.map((step, i) => (
                <div className="dk-step-row" key={i}>
                  <input
                    type="text"
                    value={step}
                    onChange={(event) => updateStep(i, event.target.value)}
                    placeholder={`Step ${i + 1}, e.g. "Click the Log In button"`}
                  />
                  {steps.length > 1 && (
                    <button type="button" className="dk-step-remove" onClick={() => removeStep(i)} aria-label="Remove step">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              <button type="button" className="dk-add-step" onClick={addStep}>
                <Plus size={13} aria-hidden="true" /> Add step
              </button>
            </div>

            <label className="dk-field">
              <span>Expected URL contains (optional)</span>
              <input
                type="text"
                value={urlContains}
                onChange={(event) => setUrlContains(event.target.value)}
                placeholder="/inventory.html"
              />
            </label>
            <label className="dk-field">
              <span>Expected page text contains (optional)</span>
              <input
                type="text"
                value={textContains}
                onChange={(event) => setTextContains(event.target.value)}
                placeholder="Products"
              />
            </label>
            <p className="dk-hint">At least one of the two above is required - it's how the Verifier confirms this workflow actually worked.</p>

            {formError && <p className="dk-error">{formError}</p>}
            {successMessage && <p className="dk-success">{successMessage}</p>}

            <button type="submit" className="dk-submit" disabled={submitting}>
              {submitting ? "Saving…" : "Save workflow"}
            </button>
          </form>
        </section>

        <section className="domain-knowledge-panel">
          <h2 className="domain-knowledge-panel-title">Registered domains</h2>
          {loading && <p className="dk-empty">Loading…</p>}
          {loadError && <p className="dk-error">{loadError}</p>}
          {!loading && !loadError && domains.length === 0 && <p className="dk-empty">No domains registered yet.</p>}
          <div className="dk-domain-list">
            {domains.map((domain) => (
              <div className="dk-domain-card" key={domain.name}>
                <div className="dk-domain-header">
                  <Globe size={13} aria-hidden="true" />
                  <span className="dk-domain-name">{domain.name}</span>
                  <span className="dk-domain-url">{domain.base_url}</span>
                </div>
                <ul className="dk-workflow-list">
                  {domain.workflows.map((w) => (
                    <li key={w.name}>
                      <span className="dk-workflow-name">{w.name}</span>
                      <span className="dk-workflow-steps">
                        {w.steps.length} step{w.steps.length === 1 ? "" : "s"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

export default DomainKnowledge;
