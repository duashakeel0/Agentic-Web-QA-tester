import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "../contexts/AuthContext";

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts unauthenticated with no stored token", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.username).toBeNull();
  });

  it("becomes authenticated after a successful login", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ token: "abc123", username: "dua" }),
    });

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login("dua", "testpass123");
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe("dua");
    expect(localStorage.getItem("qa_tester_token")).toBe("abc123");
  });

  it("throws with the server's error message on a failed login", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: "Incorrect username or password." }),
    });

    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(
      act(async () => {
        await result.current.login("dua", "wrong");
      }),
    ).rejects.toThrow("Incorrect username or password.");

    expect(result.current.isAuthenticated).toBe(false);
  });

  it("clears the token and calls the logout endpoint on logout", async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: "abc123", username: "dua" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "ok" }) });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login("dua", "testpass123");
    });

    act(() => {
      result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem("qa_tester_token")).toBeNull();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });
});
