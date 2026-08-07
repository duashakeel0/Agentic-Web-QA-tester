import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import LiveBrowserView from "../components/LiveBrowserView";
import type { ActionFrame } from "../hooks/usePipelineRun";

function actionFrame(overrides: Partial<ActionFrame> = {}): ActionFrame {
  return {
    step: "Log in",
    action: "click",
    selector: "#login-button",
    value: null,
    success: true,
    error: null,
    screenshotUrl: "/screenshots/actions/a1.png",
    targetBox: { x: 100, y: 200, width: 50, height: 20 },
    viewport: { width: 1280, height: 720 },
    timestamp: Date.now(),
    isBrokenInputAttempt: false,
    ...overrides,
  };
}

describe("LiveBrowserView", () => {
  it("shows a waiting placeholder and no LIVE badge before any frame arrives", () => {
    render(<LiveBrowserView provider="claude" frame={undefined} history={[]} />);

    expect(screen.getByText(/waiting for the explorer to act/i)).toBeInTheDocument();
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  });

  it("draws a green box for a successful action and shows the LIVE badge", () => {
    const { container } = render(<LiveBrowserView provider="claude" frame={actionFrame()} history={[actionFrame()]} />);

    expect(screen.getByText("LIVE")).toBeInTheDocument();
    const box = container.querySelector(".live-browser-box");
    expect(box).not.toBeNull();
    expect(box).not.toHaveClass("box-fail");
  });

  it("draws a red box for a failed action", () => {
    const failed = actionFrame({ success: false, error: "Timed out waiting for #login-button" });
    const { container } = render(<LiveBrowserView provider="claude" frame={failed} history={[failed]} />);

    const box = container.querySelector(".live-browser-box");
    expect(box).toHaveClass("box-fail");
    expect(screen.getByText(/Timed out waiting for #login-button/)).toBeInTheDocument();
  });

  it("draws an amber box and a testing-invalid-input tag for a broken-input probe, not a red fail", () => {
    // A deliberate broken-input probe is supposed to fail/be rejected -
    // showing it in alarming red would misread as a genuine bug, when it's
    // actually confirming the site correctly handles bad input.
    const probe = actionFrame({ success: false, error: "invalid", isBrokenInputAttempt: true });
    const { container } = render(<LiveBrowserView provider="claude" frame={probe} history={[probe]} />);

    const box = container.querySelector(".live-browser-box");
    expect(box).toHaveClass("box-probe");
    expect(box).not.toHaveClass("box-fail");
    expect(screen.getByText(/testing invalid input/i)).toBeInTheDocument();
    expect(container.querySelector(".live-browser-caption-fail")).toBeNull();
  });

  it("renders no box when the frame has no target_box (a background live tick between actions)", () => {
    const liveTick = actionFrame({ step: "", action: "live", selector: null, targetBox: null });
    const { container } = render(<LiveBrowserView provider="claude" frame={liveTick} history={[]} />);

    expect(container.querySelector(".live-browser-box")).toBeNull();
    expect(screen.getByText(/streaming the browser session/i)).toBeInTheDocument();
  });
});
