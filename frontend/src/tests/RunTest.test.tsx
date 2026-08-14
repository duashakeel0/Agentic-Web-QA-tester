import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import RunTest from "../pages/RunTest";
import { PipelineRunProvider } from "../contexts/PipelineRunContext";

const { apiGetMock } = vi.hoisted(() => ({ apiGetMock: vi.fn() }));

vi.mock("../services/api", () => ({
  apiGet: apiGetMock,
  // usePipelineRun (via PipelineRunProvider) also imports this from the
  // same module - a mock missing it throws even though this file never
  // actually starts a run.
  getPipelineSocketUrl: () => "ws://test/ws/pipeline",
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

function renderRunTest() {
  return render(
    <MemoryRouter>
      <PipelineRunProvider>
        <RunTest />
      </PipelineRunProvider>
    </MemoryRouter>,
  );
}

describe("RunTest", () => {
  it("prompts to connect Trello and disables the ticket form when it isn't connected", async () => {
    apiGetMock.mockResolvedValue({ connected: false });

    renderRunTest();

    expect(await screen.findByText(/Trello isn't connected yet/)).toBeInTheDocument();
    const link = screen.getByText("Connect Trello");
    expect(link.getAttribute("href")).toBe("/trello-settings");
    expect(screen.getByPlaceholderText("e.g. 66f2a1b3c9d4e5f6a7b8c9d0")).toBeDisabled();
    expect(screen.getByText("Start Test").closest("button")).toBeDisabled();
  });

  it("does not show the prompt and leaves the form usable when Trello is connected", async () => {
    apiGetMock.mockResolvedValue({ connected: true });

    renderRunTest();

    await screen.findByPlaceholderText("e.g. 66f2a1b3c9d4e5f6a7b8c9d0");
    expect(screen.queryByText(/Trello isn't connected yet/)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. 66f2a1b3c9d4e5f6a7b8c9d0")).not.toBeDisabled();
  });
});
