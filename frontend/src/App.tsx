// iCoDer — iCoDer Console 1:1 Routing
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
        {/* AI Studio */}
        <Route path="ai-studio" element={<AIStudioOverviewPage />} />
        <Route path="ai-studio/agents" element={<AgentsPage />} />
        <Route path="ai-studio/agents/new" element={<NewAgentPage />} />
        <Route path="ai-studio/agents/:agentId" element={<AgentDetailPage />} />
        <Route path="ai-studio/text-generation" element={<TextGenerationPage />} />
        <Route path="ai-studio/fact-extraction" element={<FactExtractionPage />} />
        <Route path="ai-studio/medical-coding" element={<MedicalCodingPage />} />
        <Route path="ai-studio/runtime" element={<RuntimeConsolePage />} />
        {/* Manage */}
        <Route path="api-clients" element={<APIClientsPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="settings" element={<SettingsPage />} />
        {/* Data */}
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
