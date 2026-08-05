import type { ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import DashboardLayout from "./layouts/DashboardLayout";
import LoginPage from "./pages/LoginPage";
import Overview from "./pages/Overview";
import PlaceholderPage from "./pages/PlaceholderPage";

function ProtectedDashboard({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <DashboardLayout>{children}</DashboardLayout>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <ProtectedDashboard>
                <Overview />
              </ProtectedDashboard>
            }
          />
          <Route
            path="/run"
            element={
              <ProtectedDashboard>
                <PlaceholderPage
                  title="Run a Test"
                  note="Live agent workflow, ticket/URL input, and model selector are coming next."
                />
              </ProtectedDashboard>
            }
          />
          <Route
            path="/history"
            element={
              <ProtectedDashboard>
                <PlaceholderPage title="History" note="The full run history table is coming next." />
              </ProtectedDashboard>
            }
          />
          <Route
            path="/compare"
            element={
              <ProtectedDashboard>
                <PlaceholderPage
                  title="Model Comparison"
                  note="Claude vs Ollama cost/latency/coverage/accuracy view is coming next."
                />
              </ProtectedDashboard>
            }
          />
          <Route
            path="/analytics"
            element={
              <ProtectedDashboard>
                <PlaceholderPage title="Analytics" note="Charts for trends over time are coming next." />
              </ProtectedDashboard>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
