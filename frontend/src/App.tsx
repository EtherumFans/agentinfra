// iCoDer — iCoDer Console 1:1 Routing
import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store';
import Layout from './components/layout/Layout';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import AIStudioOverviewPage from './pages/AIStudioOverviewPage';
import AgentsPage from './pages/AgentsPage';
import AgentDetailPage from './pages/AgentDetailPage';
import MedicalCodingPage from './pages/MedicalCodingPage';
import FactExtractionPage from './pages/FactExtractionPage';
// iCoDer M3-0.2 — P10 路由级懒加载 (Workbench / Embed 重组件单独 chunk)
const CodingReviewWorkbenchPage = lazy(() => import('./pages/CodingReviewWorkbenchPage'));
const EmbedDemoCodingReviewPage = lazy(() => import('./pages/EmbedDemoCodingReviewPage'));
import GoldCasesPage from './pages/GoldCasesPage';
import EvaluationPage from './pages/EvaluationPage';
import SettingsPage from './pages/SettingsPage';
import BillingPage from './pages/BillingPage';
import UsagePage from './pages/UsagePage';
import DeveloperQuickstartPage from './pages/DeveloperQuickstartPage';
import TextGenerationPage from './pages/TextGenerationPage';
import APIClientsPage from './pages/APIClientsPage';
import TeamPage from './pages/TeamPage';
import ExpertLibraryPage from './pages/ExpertLibraryPage';
import SupportPage from './pages/SupportPage';
import NewAgentPage from './pages/NewAgentPage';
import DocsPage from './pages/DocsPage';
import ReleaseNotesPage from './pages/ReleaseNotesPage';
import RuntimeConsolePage from './pages/RuntimeConsolePage';
import EmbeddedAssistantPage from './pages/EmbeddedAssistantPage';
import CodeTablesPage from './pages/CodeTablesPage';
import CodingDictionaryPage from './pages/CodingDictionaryPage';
import RuleLibraryPage from './pages/RuleLibraryPage';
import TicketsPage from './pages/TicketsPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import ToastContainer from './components/common/Toast';


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
        {/* Main */}
        <Route path="developer-quickstart" element={<DeveloperQuickstartPage />} />
        <Route path="docs" element={<DocsPage />} />
        <Route path="release-notes" element={<ReleaseNotesPage />} />
        {/* AI Studio (legacy — V3.0 /ai-studio/* 仍可访问，新路径 /studio/* 见下方 alias) */}
        <Route path="ai-studio" element={<AIStudioOverviewPage />} />
        <Route path="ai-studio/agents" element={<AgentsPage />} />
        <Route path="ai-studio/agents/new" element={<NewAgentPage />} />
        <Route path="ai-studio/agents/:agentId" element={<AgentDetailPage />} />
        <Route path="ai-studio/text-generation" element={<TextGenerationPage />} />
        <Route path="ai-studio/fact-extraction" element={<FactExtractionPage />} />
        <Route path="ai-studio/medical-coding" element={<MedicalCodingPage />} />
        <Route path="ai-studio/embedded-assistant" element={<EmbeddedAssistantPage />} />
        <Route path="ai-studio/runtime" element={<RuntimeConsolePage />} />
        {/* V3.0 alias — /studio/* (Studio pane) */}
        <Route path="studio" element={<AIStudioOverviewPage />} />
        <Route path="studio/agents" element={<AgentsPage />} />
        <Route path="studio/agents/new" element={<NewAgentPage />} />
        <Route path="studio/agents/:agentId" element={<AgentDetailPage />} />
        <Route path="studio/text-generation" element={<TextGenerationPage />} />
        <Route path="studio/fact-extraction" element={<FactExtractionPage />} />
        <Route path="studio/medical-coding" element={<MedicalCodingPage />} />
        <Route path="studio/agents/homepage-coding-review" element={<Suspense fallback={<div className="p-4 text-sm text-slate-500">Loading Workbench…</div>}><CodingReviewWorkbenchPage /></Suspense>} />
        <Route path="studio/marketplace" element={<AgentsPage />} />
        <Route path="studio/expert-library" element={<ExpertLibraryPage />} />
        <Route path="studio/quickstart" element={<DeveloperQuickstartPage />} />
        <Route path="studio/docs" element={<DocsPage />} />
        <Route path="studio/orchestration" element={<RuntimeConsolePage />} />
        <Route path="studio/release-notes" element={<ReleaseNotesPage />} />
        <Route path="studio/speech-to-text" element={<TextGenerationPage />} />
        <Route path="studio/embedded-assistant" element={<EmbeddedAssistantPage />} />
        <Route path="studio/new-agent" element={<NewAgentPage />} />
        {/* V3.0 alias — /runtime/* (Runtime pane) */}
        <Route path="runtime" element={<RuntimeConsolePage />} />
        <Route path="runtime/console" element={<RuntimeConsolePage />} />
        <Route path="runtime/quality" element={<EvaluationPage />} />
        <Route path="runtime/shadow-eval" element={<EvaluationPage />} />
        <Route path="runtime/adjudicator" element={<RuntimeConsolePage />} />
        <Route path="runtime/learn" element={<RuntimeConsolePage />} />
        <Route path="runtime/agents" element={<AgentsPage />} />
        <Route path="runtime/coding-review" element={<Suspense fallback={<div className="p-4 text-sm text-slate-500">Loading Workbench…</div>}><CodingReviewWorkbenchPage /></Suspense>} />
        <Route path="runtime/coding-review/:runId" element={<Suspense fallback={<div className="p-4 text-sm text-slate-500">Loading Workbench…</div>}><CodingReviewWorkbenchPage /></Suspense>} />
        <Route path="embed-demo/coding-review" element={<Suspense fallback={<div className="p-4 text-sm text-slate-500">Loading Embed…</div>}><EmbedDemoCodingReviewPage /></Suspense>} />
        <Route path="runtime/monitoring" element={<RuntimeConsolePage />} />
        {/* V3.0 alias — /manage/* (Manage pane) */}
        <Route path="manage" element={<SettingsPage />} />
        <Route path="manage/team" element={<TeamPage />} />
        <Route path="manage/usage" element={<UsagePage />} />
        <Route path="manage/billing" element={<BillingPage />} />
        <Route path="manage/settings" element={<SettingsPage />} />
        <Route path="manage/support" element={<SupportPage />} />
        <Route path="manage/audit-log" element={<ExpertLibraryPage />} />
        <Route path="manage/rule-sets" element={<ExpertLibraryPage />} />
        {/* Manage */}
        <Route path="api-clients" element={<APIClientsPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="settings" element={<SettingsPage />} />
        {/* Data */}
        <Route path="code-tables" element={<CodeTablesPage />} />
        <Route path="coding-dictionary" element={<CodingDictionaryPage />} />
        <Route path="rule-library" element={<RuleLibraryPage />} />
        <Route path="gold-cases" element={<GoldCasesPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        {/* Expert Library */}
        <Route path="expert-library" element={<ExpertLibraryPage />} />
        {/* Support */}
        <Route path="support" element={<SupportPage />} />
        <Route path="tickets" element={<TicketsPage />} />
      </Route>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}

export default App;
