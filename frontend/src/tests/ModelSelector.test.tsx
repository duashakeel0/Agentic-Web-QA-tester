import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ModelSelector from "../components/ModelSelector";

describe("ModelSelector", () => {
  it("renders all three model options", () => {
    render(<ModelSelector value="claude" onChange={() => {}} />);

    expect(screen.getByText("Claude")).toBeInTheDocument();
    expect(screen.getByText("Llama (Ollama)")).toBeInTheDocument();
    expect(screen.getByText("Compare Both")).toBeInTheDocument();
  });

  it("marks the current value's option as selected", () => {
    render(<ModelSelector value="ollama" onChange={() => {}} />);

    const ollamaOption = screen.getByRole("radio", { name: /Llama \(Ollama\)/ });
    expect(ollamaOption).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /^Claude/ })).toHaveAttribute("aria-checked", "false");
  });

  it("calls onChange with the clicked model", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ModelSelector value="claude" onChange={onChange} />);

    await user.click(screen.getByText("Compare Both"));

    expect(onChange).toHaveBeenCalledWith("both");
  });

  it("disables every option when disabled is true", () => {
    render(<ModelSelector value="claude" onChange={() => {}} disabled />);

    for (const option of screen.getAllByRole("radio")) {
      expect(option).toBeDisabled();
    }
  });
});
