import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import GlobalChat from "../components/GlobalChat";
import { PipelineRunProvider } from "../contexts/PipelineRunContext";

const { apiPostMock } = vi.hoisted(() => ({ apiPostMock: vi.fn() }));

vi.mock("../services/api", () => ({
  apiPost: apiPostMock,
  // usePipelineRun (via PipelineRunProvider) also imports this from the
  // same module - a mock missing it throws the moment start() runs, not
  // just something GlobalChat itself needs.
  getPipelineSocketUrl: () => "ws://test/ws/pipeline",
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send() {
    // no-op
  }

  close() {
    this.onclose?.();
  }
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderChat() {
  return render(
    <MemoryRouter initialEntries={["/history"]}>
      <PipelineRunProvider>
        <GlobalChat />
        <LocationDisplay />
      </PipelineRunProvider>
    </MemoryRouter>,
  );
}

describe("GlobalChat", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    apiPostMock.mockReset();
    FakeWebSocket.instances = [];
  });

  it("shows a plain chat reply without starting a run or navigating", async () => {
    apiPostMock.mockResolvedValue({
      reply: "The Explorer uses Playwright to drive a real browser.",
      action: null,
      ticket_id: null,
      model: null,
    });
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByRole("button", { name: "Open assistant" }));
    await user.type(screen.getByPlaceholderText("Type a message…"), "how does the explorer work?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("The Explorer uses Playwright to drive a real browser.")).toBeInTheDocument();
    // Stayed on the page it started on - a plain-chat reply never navigates.
    expect(screen.getByTestId("location").textContent).toBe("/history");
  });

  it("starts a run and jumps to the dashboard when the assistant detects a run-ticket intent", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    apiPostMock.mockResolvedValue({
      reply: "Starting a Claude run for ticket ABC123 now.",
      action: "run_ticket",
      ticket_id: "ABC123",
      model: "claude",
    });
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByRole("button", { name: "Open assistant" }));
    await user.type(screen.getByPlaceholderText("Type a message…"), "run ticket ABC123");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("Starting a Claude run for ticket ABC123 now.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
    // A real WebSocket connection was actually opened - the run genuinely
    // started through the shared pipeline, not just a chat message.
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("shows an error message when the chat request fails", async () => {
    apiPostMock.mockRejectedValue(new Error("network down"));
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByRole("button", { name: "Open assistant" }));
    await user.type(screen.getByPlaceholderText("Type a message…"), "hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("Could not reach the assistant right now.")).toBeInTheDocument();
  });
});
