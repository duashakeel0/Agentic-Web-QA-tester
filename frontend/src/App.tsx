import type { ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { PipelineRunProvider } from "./contexts/PipelineRunContext";
import GlobalChat from "./components/GlobalChat";
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
import Scheduler from "./pages/Scheduler";
import TrelloSettings from "./pages/TrelloSettings";

function ProtectedDashboard({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <DashboardLayout>{children}</DashboardLayout>
    </ProtectedRoute>
  );
}

function AppShell() {
  // A sibling of <Routes>, not something rendered inside a Route - so
  // navigating between pages (including the chat's own "start this
  // ticket and jump to the dashboard" action) never unmounts it and loses
  // the conversation, the same class of bug PipelineRunProvider fixed for
  // the live run itself.
  const { isAuthenticated } = useAuth();
  return (
    <>
      {isAuthenticated && <GlobalChat />}
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
        <Route
          path="/trello-settings"
          element={
            <ProtectedDashboard>
              <TrelloSettings />
            </ProtectedDashboard>
          }
        />
        <Route
          path="/scheduler"
          element={
            <ProtectedDashboard>
              <Scheduler />
            </ProtectedDashboard>
          }
        />
      </Routes>
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <PipelineRunProvider>
        <BrowserRouter>
          <AppShell />
        </BrowserRouter>
      </PipelineRunProvider>
    </AuthProvider>
  );
}

export default App;
