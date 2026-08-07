import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PipelineRunProvider, usePipelineRunContext } from "../contexts/PipelineRunContext";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }
}

function StatusReader({ label }: { label: string }) {
  const { status } = usePipelineRunContext();
  return <span data-testid={label}>{status}</span>;
}

function StartButton() {
  const { start } = usePipelineRunContext();
  return (
    <button type="button" onClick={() => start("T1", "claude")}>
      start
    </button>
  );
}

describe("PipelineRunContext", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeWebSocket.instances = [];
  });

  it("throws when a consumer is used outside a PipelineRunProvider", () => {
    function Bad() {
      usePipelineRunContext();
      return null;
    }
    // React logs its own error boundary noise for a thrown render - not
    // relevant to what this test is checking.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Bad />)).toThrow(/usePipelineRunContext must be used within/);
    spy.mockRestore();
  });

  it("keeps one live run shared across consumers, even as which consumers are mounted changes", () => {
    // Simulates what App.tsx now does: the provider sits above the router,
    // so navigating between pages swaps which consumer components are
    // mounted underneath it without the provider (and its WebSocket/state)
    // ever unmounting - unlike the old bug, where each page called
    // usePipelineRun() itself and lost everything on navigation.
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);

    const { rerender } = render(
      <PipelineRunProvider>
        <StatusReader label="dashboard-status" />
        <StartButton />
      </PipelineRunProvider>,
    );

    expect(screen.getByTestId("dashboard-status").textContent).toBe("idle");

    act(() => {
      screen.getByText("start").click();
    });
    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    expect(screen.getByTestId("dashboard-status").textContent).toBe("running");

    // "Navigate away and back" - a different consumer tree mounts under
    // the same still-alive provider.
    rerender(
      <PipelineRunProvider>
        <StatusReader label="run-test-status" />
      </PipelineRunProvider>,
    );

    expect(screen.getByTestId("run-test-status").textContent).toBe("running");
    // Only one WebSocket was ever opened - the newly-mounted consumer
    // reused the existing connection instead of starting a fresh one.
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
