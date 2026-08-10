import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import AskSiteBar from "../components/AskSiteBar";
import { PipelineRunProvider, usePipelineRunContext } from "../contexts/PipelineRunContext";

const { apiGetMock } = vi.hoisted(() => ({ apiGetMock: vi.fn() }));

vi.mock("../services/api", () => ({
  apiGet: apiGetMock,
  getPipelineSocketUrl: () => "ws://test/ws/pipeline",
  getAskSiteSocketUrl: () => "ws://test/ws/ask-site",
}));

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

function StartPipelineButton() {
  const { start } = usePipelineRunContext();
  return (
    <button type="button" onClick={() => start("T1", "claude")}>
      start run
    </button>
  );
}

describe("AskSiteBar", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeWebSocket.instances = [];
    apiGetMock.mockReset();
  });

  it("is available on the dashboard at all times, independent of any run", () => {
    apiGetMock.mockResolvedValue([]);
    render(
      <PipelineRunProvider>
        <AskSiteBar />
      </PipelineRunProvider>,
    );

    expect(screen.getByLabelText("Ask about a site")).toBeInTheDocument();
  });

  it("shows a clear decline for a query against an unrecognized domain, not a guessed answer", async () => {
    apiGetMock.mockResolvedValue([]);
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const user = userEvent.setup();

    render(
      <PipelineRunProvider>
        <AskSiteBar />
      </PipelineRunProvider>,
    );

    await user.type(screen.getByLabelText("Ask about a site"), "Does this site deliver pizza?");
    await user.keyboard("{Enter}");

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ type: "declined", reason: "No registered domain concerns pizza delivery." }),
      });
    });

    expect(screen.getByText(/No domain knowledge for this/)).toBeInTheDocument();
    expect(screen.getByText(/pizza delivery/)).toBeInTheDocument();
  });

  it("shows the answer with a domain badge for a matched query", async () => {
    apiGetMock.mockResolvedValue([]);
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const user = userEvent.setup();

    render(
      <PipelineRunProvider>
        <AskSiteBar />
      </PipelineRunProvider>,
    );

    await user.type(screen.getByLabelText("Ask about a site"), "What products does this store sell?");
    await user.keyboard("{Enter}");

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: "answer", domain: "practice_software_testing", answer: "It sells pliers, hammers, and wrenches.",
          source: "live_explore", final_url: "https://practicesoftwaretesting.com",
        }),
      });
    });

    expect(screen.getByText("practice_software_testing")).toBeInTheDocument();
    expect(screen.getByText(/pliers, hammers, and wrenches/)).toBeInTheDocument();
    expect(screen.getByText(/from a live check just now/)).toBeInTheDocument();
  });

  it("sends the just-finished run's own context when a question matches its domain", async () => {
    apiGetMock.mockResolvedValue([]);
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const user = userEvent.setup();

    render(
      <PipelineRunProvider>
        <StartPipelineButton />
        <AskSiteBar />
      </PipelineRunProvider>,
    );

    // Finish a real run for "my_site" first.
    await user.click(screen.getByText("start run"));
    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: "pipeline_done",
          provider: "claude",
          history_id: 1,
          result: {
            ticket_id: "T1", provider: "claude",
            plan: { ticket_id: "T1", ticket_title: null, matched: true, reason: null, domain: "my_site", workflow: "search", steps: [], expected_outcome: null },
            exploration: {
              ticket_id: "T1", domain: "my_site", workflow: "search", completed: true, actions: [],
              final_url: "https://my_site.example/search?q=pliers", final_page_text: "Found 1 result for pliers.", error: null,
            },
            verification: null, report: null, timings: [], metrics: null, started_at: 0, finished_at: 1, total_duration_ms: 1000,
          },
        }),
      });
    });

    // Now ask a question - it should attach the just-finished run's context.
    await user.type(screen.getByLabelText("Ask about a site"), "What did the search for pliers show?");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2));
    act(() => {
      FakeWebSocket.instances[1].onopen?.();
    });

    const sent = JSON.parse(FakeWebSocket.instances[1].sent[0]);
    expect(sent.context).toEqual({
      domain: "my_site",
      final_url: "https://my_site.example/search?q=pliers",
      final_page_text: "Found 1 result for pliers.",
      actions: [],
    });
  });
});
