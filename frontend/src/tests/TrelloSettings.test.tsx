import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import TrelloSettings from "../pages/TrelloSettings";

const { apiGetMock, apiPostMock, apiDeleteMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
  apiDeleteMock: vi.fn(),
}));

vi.mock("../services/api", () => ({
  apiGet: apiGetMock,
  apiPost: apiPostMock,
  apiDelete: apiDeleteMock,
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

describe("TrelloSettings", () => {
  it("shows Not connected when nothing is configured", async () => {
    apiGetMock.mockResolvedValue({ connected: false, source: "none" });

    render(<TrelloSettings />);

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.queryByText("Disconnect")).not.toBeInTheDocument();
  });

  it("shows the dashboard-connected status and a Disconnect button when source is settings", async () => {
    apiGetMock.mockResolvedValue({ connected: true, source: "settings" });

    render(<TrelloSettings />);

    expect(await screen.findByText("Connected from this dashboard")).toBeInTheDocument();
    expect(screen.getByText("Disconnect")).toBeInTheDocument();
  });

  it("shows an env-var hint and no Disconnect button when source is env", async () => {
    apiGetMock.mockResolvedValue({ connected: true, source: "env" });

    render(<TrelloSettings />);

    expect(await screen.findByText("Connected via a backend environment variable")).toBeInTheDocument();
    expect(screen.queryByText("Disconnect")).not.toBeInTheDocument();
    expect(screen.getByText(/backend's own environment variables/)).toBeInTheDocument();
  });

  it("rejects submitting with empty fields without calling the API", async () => {
    apiGetMock.mockResolvedValue({ connected: false, source: "none" });
    const user = userEvent.setup();

    render(<TrelloSettings />);
    await screen.findByText("Not connected");

    await user.click(screen.getByText("Save connection"));

    expect(screen.getByText("Both an API key and a token are required.")).toBeInTheDocument();
    expect(apiPostMock).not.toHaveBeenCalled();
  });

  it("saves a new connection and reloads status", async () => {
    apiGetMock
      .mockResolvedValueOnce({ connected: false, source: "none" })
      .mockResolvedValueOnce({ connected: true, source: "settings" });
    apiPostMock.mockResolvedValue({ connected: true, source: "settings" });
    const user = userEvent.setup();

    render(<TrelloSettings />);
    await screen.findByText("Not connected");

    await user.type(screen.getByPlaceholderText("Your Trello API key"), "  real-key  ");
    await user.type(screen.getByPlaceholderText("Your Trello token"), "  real-token  ");
    await user.click(screen.getByText("Save connection"));

    await waitFor(() =>
      expect(apiPostMock).toHaveBeenCalledWith("/api/trello/settings", { api_key: "real-key", token: "real-token" }),
    );
    expect(await screen.findByText(/Trello connected/)).toBeInTheDocument();
    expect(await screen.findByText("Connected from this dashboard")).toBeInTheDocument();
  });

  it("disconnects and reloads status", async () => {
    apiGetMock
      .mockResolvedValueOnce({ connected: true, source: "settings" })
      .mockResolvedValueOnce({ connected: false, source: "none" });
    apiDeleteMock.mockResolvedValue({ connected: false, source: "none" });
    const user = userEvent.setup();

    render(<TrelloSettings />);
    await screen.findByText("Connected from this dashboard");

    await user.click(screen.getByText("Disconnect"));

    await waitFor(() => expect(apiDeleteMock).toHaveBeenCalledWith("/api/trello/settings"));
    expect(await screen.findByText("Not connected")).toBeInTheDocument();
  });
});
