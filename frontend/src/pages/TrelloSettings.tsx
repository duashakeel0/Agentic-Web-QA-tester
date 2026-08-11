import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, ExternalLink, XCircle } from "lucide-react";
import { apiDelete, apiGet, apiPost, ApiError } from "../services/api";
import "./TrelloSettings.css";

interface TrelloStatus {
  connected: boolean;
  source: "settings" | "env" | "none";
}

const SOURCE_LABEL: Record<TrelloStatus["source"], string> = {
  settings: "Connected from this dashboard",
  env: "Connected via a backend environment variable",
  none: "Not connected",
};

/** Lets a Trello API key/token be set up entirely from the dashboard
 * instead of requiring backend .env file access - closes the gap a
 * hosted, non-technical user would otherwise hit. One shared connection
 * at a time (this app has one login, not per-user accounts) - saving a
 * new one replaces whatever was previously connected. */
function TrelloSettings() {
  const [status, setStatus] = useState<TrelloStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [apiKey, setApiKey] = useState("");
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  function load() {
    setLoading(true);
    apiGet<TrelloStatus>("/api/trello/status")
      .then((data) => {
        setStatus(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load Trello connection status."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    if (!apiKey.trim() || !token.trim()) {
      setFormError("Both an API key and a token are required.");
      return;
    }

    setSubmitting(true);
    try {
      await apiPost<TrelloStatus>("/api/trello/settings", { api_key: apiKey.trim(), token: token.trim() });
      setSuccessMessage("Trello connected - tickets from your board can be run right away, no restart needed.");
      setApiKey("");
      setToken("");
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not save these credentials.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    setFormError(null);
    setSuccessMessage(null);
    try {
      await apiDelete<TrelloStatus>("/api/trello/settings");
      setSuccessMessage("Trello disconnected.");
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not disconnect.");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="trello-settings-page">
      <h1 className="trello-settings-title">Trello Settings</h1>
      <p className="trello-settings-subtitle">
        Connect the Trello board your tickets live on - once saved, ticket IDs can be run right away, no backend
        file access or restart needed.
      </p>

      <div className="trello-settings-layout">
        <section className="trello-settings-panel">
          <h2 className="trello-settings-panel-title">Connect Trello</h2>
          <form className="trello-settings-form" onSubmit={handleSubmit}>
            <label className="ts-field">
              <span>API key</span>
              <input
                type="text"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="Your Trello API key"
                autoComplete="off"
              />
            </label>
            <label className="ts-field">
              <span>Token</span>
              <input
                type="password"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="Your Trello token"
                autoComplete="off"
              />
            </label>
            <a
              className="ts-trello-link"
              href="https://trello.com/app-key"
              target="_blank"
              rel="noreferrer"
            >
              Get your API key and token from Trello <ExternalLink size={12} aria-hidden="true" />
            </a>

            {formError && <p className="ts-error">{formError}</p>}
            {successMessage && <p className="ts-success">{successMessage}</p>}

            <button type="submit" className="ts-submit" disabled={submitting}>
              {submitting ? "Saving…" : "Save connection"}
            </button>
          </form>
        </section>

        <section className="trello-settings-panel">
          <h2 className="trello-settings-panel-title">Connection status</h2>
          {loading && <p className="ts-empty">Loading…</p>}
          {loadError && <p className="ts-error">{loadError}</p>}
          {!loading && !loadError && status && (
            <div className={`ts-status-card ${status.connected ? "ts-status-connected" : "ts-status-disconnected"}`}>
              {status.connected ? (
                <CheckCircle2 size={16} aria-hidden="true" />
              ) : (
                <XCircle size={16} aria-hidden="true" />
              )}
              <span>{SOURCE_LABEL[status.source]}</span>
            </div>
          )}
          {status?.source === "settings" && (
            <button type="button" className="ts-disconnect" onClick={handleDisconnect} disabled={disconnecting}>
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </button>
          )}
          {status?.source === "env" && (
            <p className="ts-hint">
              This connection comes from the backend's own environment variables, not from this page - saving a new
              one above will take over instead.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

export default TrelloSettings;
