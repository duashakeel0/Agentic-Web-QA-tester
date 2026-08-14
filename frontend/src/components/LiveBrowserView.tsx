import type { CSSProperties } from "react";
import { Camera, FlaskConical, ImageOff } from "lucide-react";
import { API_BASE_URL } from "../config";
import type { ActionFrame } from "../hooks/usePipelineRun";
import type { Provider } from "../types/pipeline";
import "./LiveBrowserView.css";

const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Llama (Ollama)" };

function screenshotSrc(url: string | null): string | undefined {
  return url ? `${API_BASE_URL}${url}` : undefined;
}

/** A deliberate broken-input probe is *supposed* to fail (or be rejected) -
 * neither a pass nor a real failure in the "did the workflow work" sense,
 * so it gets its own neutral tone instead of the alarming red a genuine
 * failed action gets. */
function frameTone(frame: ActionFrame): "pass" | "fail" | "probe" {
  if (frame.isBrokenInputAttempt) return "probe";
  return frame.success ? "pass" : "fail";
}

/** Scales the Explorer's viewport-pixel target_box down to a percentage box
 * that sits correctly over the screenshot <img> regardless of how large the
 * browser renders it - the box and the screenshot were captured against the
 * exact same viewport, so a plain ratio is all that's needed. */
function boxStyle(frame: ActionFrame): CSSProperties | null {
  if (!frame.targetBox || !frame.viewport || frame.viewport.width === 0 || frame.viewport.height === 0) return null;
  const { x, y, width, height } = frame.targetBox;
  const { width: vw, height: vh } = frame.viewport;
  return {
    left: `${(x / vw) * 100}%`,
    top: `${(y / vh) * 100}%`,
    width: `${(width / vw) * 100}%`,
    height: `${(height / vh) * 100}%`,
  };
}

function LiveBrowserView({
  provider,
  frame,
  history,
}: {
  provider: Provider;
  frame: ActionFrame | undefined;
  history: ActionFrame[];
}) {
  const overlay = frame ? boxStyle(frame) : null;
  const tone = frame ? frameTone(frame) : null;

  return (
    <div className="live-browser-view">
      <div className="live-browser-view-header">
        <Camera size={13} aria-hidden="true" />
        <span>Live Browser</span>
        {frame && (
          <span className="live-browser-live-dot" aria-label="Live">
            <span className="live-browser-live-pulse" aria-hidden="true" />
            LIVE
          </span>
        )}
        <span className={`live-browser-provider-tag live-browser-provider-${provider}`}>{PROVIDER_LABELS[provider]}</span>
      </div>

      {!frame ? (
        <div className="live-browser-empty">
          <Camera size={22} aria-hidden="true" />
          <p>Waiting for the Explorer to act…</p>
        </div>
      ) : (
        <>
          <div className="live-browser-frame">
            {frame.screenshotUrl ? (
              <img src={screenshotSrc(frame.screenshotUrl)} alt={`${frame.action} on ${PROVIDER_LABELS[provider]}`} />
            ) : (
              <div className="live-browser-frame-placeholder">
                <ImageOff size={20} aria-hidden="true" />
              </div>
            )}
            {overlay && <div className={`live-browser-box box-${tone}`} style={overlay} />}
          </div>
          {frame.step ? (
            <p className={`live-browser-caption${tone === "fail" ? " live-browser-caption-fail" : ""}`}>
              {tone === "probe" && (
                <span className="live-browser-probe-tag">
                  <FlaskConical size={11} aria-hidden="true" /> Testing invalid input
                </span>
              )}
              <strong>{frame.step}</strong>
              {" — "}
              {frame.action}
              {frame.selector ? ` on ${frame.selector}` : ""}
              {tone === "fail" && frame.error ? ` — ${frame.error}` : ""}
            </p>
          ) : (
            <p className="live-browser-caption">Streaming the browser session…</p>
          )}

          {history.length > 1 && (
            <div className="live-browser-filmstrip" aria-label="Recent actions">
              {history.map((f, i) => (
                <img
                  key={i}
                  src={screenshotSrc(f.screenshotUrl)}
                  alt=""
                  className={`live-browser-thumb${frameTone(f) === "fail" ? " live-browser-thumb-fail" : ""}${f === frame ? " live-browser-thumb-active" : ""}`}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default LiveBrowserView;
