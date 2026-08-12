import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

const PENDING_KEY_STORAGE = "trello_connect_pending_api_key";

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/trello-settings");
});

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

  it("shows an inline error and does not navigate if Connect with Trello is clicked with no API key", async () => {
    apiGetMock.mockResolvedValue({ connected: false, source: "none" });
    const user = userEvent.setup();

    render(<TrelloSettings />);
    await screen.findByText("Not connected");

    await user.click(screen.getByText("Connect with Trello"));

    expect(screen.getByText("Enter your API key first, then click Connect with Trello.")).toBeInTheDocument();
    expect(sessionStorage.getItem(PENDING_KEY_STORAGE)).toBeNull();
  });

  it("stashes the API key and sends the browser to Trello's real authorize page", async () => {
    apiGetMock.mockResolvedValue({ connected: false, source: "none" });
    const user = userEvent.setup();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", { writable: true, value: { ...originalLocation, href: "" } });

    render(<TrelloSettings />);
    await screen.findByText("Not connected");

    await user.type(screen.getByPlaceholderText("Your Trello API key"), "my-real-key");
    await user.click(screen.getByText("Connect with Trello"));

    expect(sessionStorage.getItem(PENDING_KEY_STORAGE)).toBe("my-real-key");
    expect(window.location.href).toContain("https://trello.com/1/authorize");
    expect(window.location.href).toContain("key=my-real-key");
    expect(window.location.href).toContain("response_type=token");

    Object.defineProperty(window, "location", { writable: true, value: originalLocation });
  });

  it("auto-saves the token Trello approved when returning with a stashed API key", async () => {
    sessionStorage.setItem(PENDING_KEY_STORAGE, "stashed-key");
    window.history.replaceState(null, "", "/trello-settings#token=granted-token");
    apiGetMock
      .mockResolvedValueOnce({ connected: false, source: "none" })
      .mockResolvedValueOnce({ connected: true, source: "settings" });
    apiPostMock.mockResolvedValue({ connected: true, source: "settings" });

    render(<TrelloSettings />);

    await waitFor(() =>
      expect(apiPostMock).toHaveBeenCalledWith("/api/trello/settings", {
        api_key: "stashed-key",
        token: "granted-token",
      }),
    );
    expect(await screen.findByText(/Trello connected/)).toBeInTheDocument();
    expect(sessionStorage.getItem(PENDING_KEY_STORAGE)).toBeNull();
    expect(window.location.hash).toBe("");
  });

  it("shows an error instead of saving if the API key was lost across the redirect", async () => {
    window.history.replaceState(null, "", "/trello-settings#token=granted-token");
    apiGetMock.mockResolvedValue({ connected: false, source: "none" });

    render(<TrelloSettings />);

    expect(
      await screen.findByText(/the API key used to start it was lost/),
    ).toBeInTheDocument();
    expect(apiPostMock).not.toHaveBeenCalled();
  });
});
