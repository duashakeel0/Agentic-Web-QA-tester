import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProtectedRoute from "../components/ProtectedRoute";

const mockUseAuth = vi.fn();
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>Login Screen</div>} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <div>Secret Dashboard</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("redirects to /login when not authenticated", () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false });

    renderAt("/");

    expect(screen.getByText("Login Screen")).toBeInTheDocument();
    expect(screen.queryByText("Secret Dashboard")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true });

    renderAt("/");

    expect(screen.getByText("Secret Dashboard")).toBeInTheDocument();
  });
});
