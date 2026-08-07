import type { ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { PipelineRunProvider } from "./contexts/PipelineRunContext";
import ProtectedRoute from "./components/ProtectedRoute";
import DashboardLayout from "./layouts/DashboardLayout";
import Analytics from "./pages/Analytics";
import Compare from "./pages/Compare";
import Dashboard from "./pages/Dashboard";
import DomainKnowledge from "./pages/DomainKnowledge";
import History from "./pages/History";
import HistoryReport from "./pages/HistoryReport";
import LoginPage from "./pages/LoginPage";
import RunTest from "./pages/RunTest";

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
      <PipelineRunProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <ProtectedDashboard>
                  <Dashboard />
                </ProtectedDashboard>
              }
            />
            <Route
              path="/run"
              element={
                <ProtectedDashboard>
                  <RunTest />
                </ProtectedDashboard>
              }
            />
            <Route
              path="/history"
              element={
                <ProtectedDashboard>
                  <History />
                </ProtectedDashboard>
              }
            />
            <Route
              path="/history/:id"
              element={
                <ProtectedDashboard>
                  <HistoryReport />
                </ProtectedDashboard>
              }
            />
            <Route
              path="/compare"
              element={
                <ProtectedDashboard>
                  <Compare />
                </ProtectedDashboard>
              }
            />
            <Route
              path="/analytics"
              element={
                <ProtectedDashboard>
                  <Analytics />
                </ProtectedDashboard>
              }
            />
            <Route
              path="/domain-knowledge"
              element={
                <ProtectedDashboard>
                  <DomainKnowledge />
                </ProtectedDashboard>
              }
            />
          </Routes>
        </BrowserRouter>
      </PipelineRunProvider>
    </AuthProvider>
  );
}

export default App;
