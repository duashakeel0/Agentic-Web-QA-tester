import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { API_BASE_URL } from "../config";
import { tokenStorage } from "../services/tokenStorage";

interface AuthContextValue {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStorage.getToken());
  const [username, setUsername] = useState<string | null>(() => tokenStorage.getUsername());

  const login = useCallback(async (username: string, password: string) => {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail || "Login failed - check your username and password.");
    }

    const data = (await response.json()) as { token: string; username: string };
    tokenStorage.set(data.token, data.username);
    setToken(data.token);
    setUsername(data.username);
  }, []);

  const logout = useCallback(() => {
    const currentToken = tokenStorage.getToken();
    tokenStorage.clear();
    setToken(null);
    setUsername(null);

    if (currentToken) {
      fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${currentToken}` },
      }).catch(() => {
        // Best-effort - the client-side token is already cleared either way.
      });
    }
  }, []);

  const value = useMemo(
    () => ({ token, username, isAuthenticated: token !== null, login, logout }),
    [token, username, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return ctx;
}
