import { Navigate, Route, Routes } from "react-router-dom";
import { TopBar } from "./TopBar";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { AgentsPage } from "../pages/AgentsPage";
import { AgentDetailPage } from "../pages/AgentDetailPage";
import { QuickstartPage } from "../pages/QuickstartPage";

export function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only rounded-lg bg-panel px-3 py-2 text-sm font-medium text-ink shadow-lift focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50"
      >
        跳到主内容
      </a>
      <TopBar />
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<AgentsPage />} />
            <Route path="/quickstart" element={<QuickstartPage />} />
            {/* agent ids contain a slash (icoder/...), so capture the rest of the path */}
            <Route path="/agents/*" element={<AgentDetailPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </main>
      {/* Always-on deployment-integrity statement: iCoDer's core differentiator vs.
          cloud coding tools is that PHI never leaves the hospital. A quiet, persistent
          footer (not nav) keeps that trust signal in front of IT / compliance buyers. */}
      <footer className="border-t border-line">
        <div className="mx-auto w-full max-w-6xl px-6 py-5">
          <p className="text-center text-xs text-faint">
            iCoDer · 医疗收入合规 AI Runtime · 院内私有化部署 · 数据不出院 · PHI 服务端脱敏 · 生产写回锁定
          </p>
        </div>
      </footer>
    </div>
  );
}
