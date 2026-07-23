// iCoDer - iCoDer Console routing.
// Phase 2026-06-29: Doctor / MethodCompare / RunTrace / Marketplace / old
// AgentHub pages deleted. Routes into /runtime/doctor, /runtime/method-compare,
// /runtime/runs, /runtime/agent-hub, /marketplace removed. The legacy /studio/
// and /manage/ aliases remain as no-op redirects so old links don't 404 while
// Task #4 rewrites the sidebar to align with Corti's IA.
//
// Phase 3-B2 Loop 0 (2026-07-05): TextGeneration and EmbeddedAssistant routes
// removed (Corti parity - these concepts are replaced by the upcoming Chat
// flow and Agent Hub). Old paths redirect to /ai-studio/agents so deep links
// don't 404. TextGeneration file is kept on disk as an orphan file in case
// of implicit dependencies; the embedded-assistant page is physically deleted.
// Phase 4-F2 (2026-07-10): RunTrace route is RESTORED — the dedicated trace
// viewer is required by §4.3 to display trace_events from the unified endpoint.
import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store';
import Layout from './components/layout/Layout';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import AIStudioOverviewPage from './pages/AIStudioOverviewPage';
import AgentsPage from './pages/AgentsPage';
import AgentDetailPage from './pages/AgentDetailPage';
import AgentChatPage from './pages/AgentChatPage';
import MedicalCodingPage from './pages/MedicalCodingPage';
import CodingComplianceWorkbenchPage from './pages/CodingComplianceWorkbenchPage';
import CDIWorkbenchPage from './pages/CDIWorkbenchPage';
import FactExtractionPage from './pages/FactExtractionPage';
import EmbeddedAssistantPage from './pages/EmbeddedAssistantPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import ToastContainer from './components/common/Toast';
import SettingsPage from './pages/SettingsPage';
import BillingPage from './pages/BillingPage';
import UsagePage from './pages/UsagePage';
import CustomersPage from './pages/CustomersPage';
import TemplatesPage from './pages/TemplatesPage';
import TicketsPage from './pages/TicketsPage';
import RunTracePage from './pages/RunTracePage';

const DeveloperQuickstartPage = lazy(() => import('./pages/DeveloperQuickstartPage'));
const NewAgentPage = lazy(() => import('./pages/NewAgentPage'));
const DocsPage = lazy(() => import('./pages/DocsPage'));
const ReleaseNotesPage = lazy(() => import('./pages/ReleaseNotesPage'));
const SupportPage = lazy(() => import('./pages/SupportPage'));
const APIClientsPage = lazy(() => import('./pages/APIClientsPage'));
const TeamPage = lazy(() => import('./pages/TeamPage'));
const ExpertsPage = lazy(() => import('./pages/ExpertsPage'));


function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function App() {
  const { isAuthenticated } = useAuthStore();

  return (
    <>
    <ToastContainer />
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<HomePage />} />
        <Route path="developer-quickstart" element={<DeveloperQuickstartPage />} />
        <Route path="docs" element={<DocsPage />} />
        <Route path="release-notes" element={<ReleaseNotesPage />} />

        {/* AI Studio */}
        <Route path="ai-studio" element={<AIStudioOverviewPage />} />
        <Route path="ai-studio/agents" element={<AgentsPage />} />
        <Route path="ai-studio/agents/new" element={<NewAgentPage />} />
        <Route path="ai-studio/experts" element={<ExpertsPage />} />
        <Route path="ai-studio/agents/:agentId" element={<AgentDetailPage />} />
        {/* Phase 4-D - Corti-style chat URL: /ai-studio/agents/:agentId/chat */}
        <Route path="ai-studio/agents/:agentId/chat" element={<AgentChatPage />} />
        {/* Phase 3-B2 Loop 2 - Click-to-Chat UX (Gap 2.2). Legacy route redirects. */}
        <Route path="agents/:project_agent_id/chat" element={<AgentChatPage />} />
        {/* Phase 3-D1 Task 4 - RunTrace Corti-parity Viewer (9-step timeline).
            Openable from AgentChatPage via the "View RunTrace" button. */}
        <Route path="runs/:runId/trace" element={<RunTracePage />} />
        {/* Phase 3-B2 Loop 0: TextGeneration + EmbeddedAssistant routes removed.
            Old paths redirect to /ai-studio/agents (Agent Hub). */}
        <Route path="ai-studio/text-generation" element={<Navigate to="/ai-studio/agents" replace />} />
        <Route path="ai-studio/embedded-assistant" element={<EmbeddedAssistantPage />} />
        <Route path="ai-studio/fact-extraction" element={<FactExtractionPage />} />
        <Route path="ai-studio/medical-coding" element={<MedicalCodingPage />} />
        {/* Phase 5 Track C Gate 5 — 7-stage coding compliance mainline workbench */}
        <Route path="ai-studio/coding-compliance" element={<CodingComplianceWorkbenchPage />} />
        {/* Phase 5 Track D Gate 7 — CDI 3-pane workbench + Physician Response Panel */}
        <Route path="ai-studio/cdi" element={<CDIWorkbenchPage />} />

        {/* V3.0 alias - /studio/* */}
        <Route path="studio" element={<AIStudioOverviewPage />} />
        <Route path="studio/agents" element={<AgentsPage />} />
        <Route path="studio/agents/new" element={<NewAgentPage />} />
        <Route path="studio/agents/:agentId" element={<AgentDetailPage />} />
        <Route path="studio/text-generation" element={<Navigate to="/ai-studio/agents" replace />} />
        <Route path="studio/fact-extraction" element={<FactExtractionPage />} />
        <Route path="studio/medical-coding" element={<MedicalCodingPage />} />
        {/* homepage-coding-review shim: legacy route → medical-coding */}
        <Route path="studio/agents/homepage-coding-review" element={<Navigate to="/runtime/coding-review" replace />} />
        <Route path="studio/quickstart" element={<DeveloperQuickstartPage />} />
        <Route path="studio/docs" element={<DocsPage />} />
        <Route path="studio/release-notes" element={<ReleaseNotesPage />} />
        <Route path="studio/speech-to-text" element={<Navigate to="/ai-studio/agents" replace />} />
        <Route path="studio/embedded-assistant" element={<EmbeddedAssistantPage />} />
        <Route path="studio/new-agent" element={<NewAgentPage />} />

        {/* Runtime - only MedicalCoding remains. RuntimeConsole / Runs / Doctor
            are iCoDer-internal concepts with no Corti equivalent; quality +
            shadow-eval pages are pending Corti Mapping (see Task #4). */}
        <Route path="runtime/agents" element={<AgentsPage />} />
        <Route path="runtime/coding-review" element={<MedicalCodingPage />} />
        <Route path="runtime/coding-review/:runId" element={<MedicalCodingPage />} />

        {/* Manage */}
        <Route path="manage" element={<SettingsPage />} />
        <Route path="manage/team" element={<TeamPage />} />
        <Route path="manage/usage" element={<UsagePage />} />
        <Route path="manage/billing" element={<BillingPage />} />
        <Route path="manage/customers" element={<CustomersPage />} />
        <Route path="manage/templates" element={<TemplatesPage />} />
        <Route path="manage/settings" element={<SettingsPage />} />
        <Route path="manage/support" element={<SupportPage />} />

        {/* Support */}
        <Route path="support" element={<SupportPage />} />
        <Route path="tickets" element={<TicketsPage />} />
        <Route path="api-clients" element={<APIClientsPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="customers" element={<CustomersPage />} />
        <Route path="templates" element={<TemplatesPage />} />
        <Route path="settings" element={<SettingsPage />} />

        <Route path="support" element={<SupportPage />} />
      </Route>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}

export default App;
