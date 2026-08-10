import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import DomainKnowledge from "../pages/DomainKnowledge";

const { apiGetMock, apiPostMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
}));

vi.mock("../services/api", () => ({
  apiGet: apiGetMock,
  apiPost: apiPostMock,
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

const existingDomain = {
  name: "parabank",
  base_url: "https://parabank.parasoft.com/parabank/index.htm",
  workflows: [
    { name: "login", steps: ["Navigate", "Log in"], expected_outcome: { url_contains: "overview.htm", text_contains: null } },
  ],
};

describe("DomainKnowledge", () => {
  it("lists the registered domains and their workflows", async () => {
    apiGetMock.mockResolvedValue([existingDomain]);

    render(<DomainKnowledge />);

    expect(await screen.findByText("parabank")).toBeInTheDocument();
    expect(screen.getByText("login")).toBeInTheDocument();
    expect(screen.getByText("2 steps")).toBeInTheDocument();
  });

  it("rejects a submission with no url_contains or text_contains", async () => {
    apiGetMock.mockResolvedValue([]);
    const user = userEvent.setup();

    render(<DomainKnowledge />);
    await waitFor(() => expect(apiGetMock).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g. parabank/), "New Site");
    await user.type(screen.getByPlaceholderText("https://example.com"), "https://newsite.example.com");
    await user.type(screen.getByPlaceholderText("e.g. request_loan"), "do_a_thing");
    await user.type(screen.getByPlaceholderText(/Step 1/), "Click something");
    await user.click(screen.getByRole("button", { name: /save workflow/i }));

    expect(await screen.findByText(/Provide at least one/)).toBeInTheDocument();
    expect(apiPostMock).not.toHaveBeenCalled();
  });

  it("submits a new workflow and shows a success message", async () => {
    apiGetMock.mockResolvedValue([]);
    apiPostMock.mockResolvedValue({
      name: "new_site",
      base_url: "https://newsite.example.com",
      workflows: [{ name: "do_a_thing", steps: ["Click something"], expected_outcome: { url_contains: null, text_contains: "Done" } }],
    });
    const user = userEvent.setup();

    render(<DomainKnowledge />);
    await waitFor(() => expect(apiGetMock).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/e.g. parabank/), "New Site");
    await user.type(screen.getByPlaceholderText("https://example.com"), "https://newsite.example.com");
    await user.type(screen.getByPlaceholderText("e.g. request_loan"), "do_a_thing");
    await user.type(screen.getByPlaceholderText(/Step 1/), "Click something");
    await user.type(screen.getByPlaceholderText("Products"), "Done");
    await user.click(screen.getByRole("button", { name: /save workflow/i }));

    expect(await screen.findByText(/Saved "do_a_thing" to new_site/)).toBeInTheDocument();
    expect(apiPostMock).toHaveBeenCalledWith(
      "/api/domains",
      expect.objectContaining({
        domain: "New Site",
        base_url: "https://newsite.example.com",
        workflow: expect.objectContaining({ name: "do_a_thing", steps: ["Click something"], text_contains: "Done" }),
      }),
    );
  });
});
