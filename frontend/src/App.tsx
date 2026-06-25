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
// iCoDer Phase A A2 (2026-06-25): CodingReviewWorkbenchPage.tsx deleted
// because it imported non-existent components. Its 3 routes now alias
// to MedicalCodingPage. The legacy CodingReviewWorkbenchPage was a 14-stage
// cosmetic view of homepage-coding-review; the real workbench UI is
// MedicalCodingPage (DiagnosisCard + EvidenceHighlighter + TopKChips).
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
import MethodComparePage from './pages/MethodComparePage';
// Phase A A2 (2026-06-25): CodeTablesPage, CodingDictionaryPage,
// RuleLibraryPage, TicketsPage never existed in the new Runtime — they
// were legacy "data/library" surface stubs from a 1:1 Corti mirror that
// never landed. The canonical equivalents are:
//   - 编码表 (code-tables)    → /gold-cases (GoldCasesPage) + /evaluation
//   - 编码字典 (coding-dict)   → GoldCasesPage (gold standard codes)
//   - 规则库 (rule-library)   → ExpertLibraryPage (rule_set registry)
//   - 工单 (tickets)          → /support (SupportPage)
// Per the rule "不允许继续扩大 legacy 双路径", we do not recreate them.
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
        {/* Phase A A3 (2026-06-25): legacy homepage-coding-review route
            redirected to MedicalCodingPage. The 14-stage cosmetic
            CodingReviewWorkbenchPage is gone. */}
        <Route path="studio/agents/homepage-coding-review" element={<MedicalCodingPage />} />
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
        {/* Phase A A2: CodingReviewWorkbenchPage deleted; aliased to MedicalCodingPage. */}
        <Route path="runtime/coding-review" element={<MedicalCodingPage />} />
        <Route path="runtime/coding-review/:runId" element={<MedicalCodingPage />} />
        <Route path="runtime/method-compare" element={<MethodComparePage />} />
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
        {/* Data — Phase A A2: 4 legacy "data/library" pages removed.
            The real surfaces are gold-cases (gold standard) and
            evaluation (runtime quality), both already wired. */}
        <Route path="gold-cases" element={<GoldCasesPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        {/* Expert Library */}
        <Route path="expert-library" element={<ExpertLibraryPage />} />
        {/* Support */}
        <Route path="support" element={<SupportPage />} />
      </Route>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}

export default App;
