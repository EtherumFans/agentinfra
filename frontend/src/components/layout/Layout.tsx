// iCoDer Layout — iCoDer Console exact replica
// Global header (64px) + Sidebar (w/ project selector, nav groups, footer) + Main
import { useState, useEffect } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore, useThemeStore } from '../../store';
import { BACKEND_BASE_URL } from '../../config';
import { oauthApi } from '../../services/api';
import { useT, useLocaleStore } from '../../i18n';
import OrgSwitcher from './OrgSwitcher';
import { ErrorBoundary } from '../common/ErrorBoundary';
import {
  PanelLeftClose, PanelLeft, Home, FlaskConical,
  Mic, AlignLeft, Sparkles, ListTree, Asterisk, BrainCircuit,
  KeyRound, Users, CreditCard, ChartNoAxesColumn, Settings,
  ArrowUpRight, Bell,
  ChevronDown, Rocket, Layers, Folder, ChevronsUpDown, Database,
  Terminal, Stethoscope, Users2, FileText, MessageSquare,
} from 'lucide-react';

const PROJECT_SLUG = 'icoder-medical-coding';
const DEFAULT_PROJECT_NAME = 'iCoDer Console';

function loadProjectName(): string {
  try { return localStorage.getItem('icoder-project-name') || DEFAULT_PROJECT_NAME; } catch { return DEFAULT_PROJECT_NAME; }
}
function saveProjectName(name: string) {
  try { localStorage.setItem('icoder-project-name', name); } catch {}
}

export default function Layout() {
  const { user, logout } = useAuthStore();
  const t = useT();
  const locale = useLocaleStore(s => s.locale);
  const setLocale = useLocaleStore(s => s.setLocale);
  const [collapsed, setCollapsed] = useState(false);
  const [showNotif, setShowNotif] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showProjectMenu, setShowProjectMenu] = useState(false);
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [selectedClient, setSelectedClient] = useState<string>(PROJECT_SLUG);
  const [projectName, setProjectName] = useState(loadProjectName);
  const [editingProjectName, setEditingProjectName] = useState(false);
  const navigate = useNavigate();

  // Navigation matches iCoDer Console exactly
  const topItems = [
    { to: '/', label: t.home, icon: Home, end: true },
    { to: '/developer-quickstart', label: t.developerQuickstart, icon: Rocket },
  ];

  const navSections = [
    {
      name: t.aiStudio,
      items: [
        { to: '/ai-studio', label: t.overview, icon: FlaskConical, end: true },
        { to: '/ai-studio/agents', label: t.agents, icon: Layers },
        { to: '/ai-studio/fact-extraction', label: t.factExtraction, icon: ListTree },
        { to: '/ai-studio/medical-coding', label: t.medicalCoding, icon: Asterisk },
      ],
    },
    {
      name: 'Runtime',
      items: [
        { to: '/runtime/coding-review', label: 'Medical Coding', icon: Stethoscope, end: false },
      ],
    },
    {
      name: t.manage,
      items: [
        { to: '/api-clients', label: t.apiClients, icon: KeyRound },
        { to: '/team', label: t.team, icon: Users },
        { to: '/customers', label: t.customersTitle, icon: Users2 },
        { to: '/templates', label: t.templatesTitle, icon: FileText },
        { to: '/billing', label: t.billing, icon: CreditCard },
        { to: '/usage', label: t.usage, icon: ChartNoAxesColumn },
        { to: '/settings', label: t.settings, icon: Settings },
      ],
    },
    {
      name: t.data,
      items: [
        { to: '/gold-cases', label: t.goldCases, icon: Sparkles },
        { to: '/evaluation', label: t.evaluation, icon: ChartNoAxesColumn },
        { to: '/expert-library', label: t.expertLibrary, icon: BrainCircuit },
      ],
    },
    {
      name: t.support,
      items: [
        { to: '/support', label: t.getHelp, icon: MessageSquare },
        { to: '/tickets', label: t.ticketsTitle, icon: FileText, external: true, end: false },
      ],
    },
  ];

  // Fetch API clients for project dropdown
  useEffect(() => {
    oauthApi.list().then((r: any) => {
      setApiClients(r.data?.clients || []);
    }).catch(() => {});
  }, []);

  const initials = user?.full_name
    ? user.full_name.slice(0, 2).toUpperCase()
    : '??';

  const theme = useThemeStore(s => s.theme);
  const toggleTheme = useThemeStore(s => s.toggleTheme);

  const ThemeToggle = () => (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      )}
    </button>
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* ====== Global Header (64px) ====== */}
      <header className="flex h-16 shrink-0 items-center gap-2 border-b border-border px-4">
        <div className="flex items-center justify-between w-full">
          <a href="/" className="flex items-center gap-2 text-lg font-brand text-foreground hover:opacity-80 transition-opacity">
            <div className="w-6 h-6 rounded bg-primary flex items-center justify-center">
              <Asterisk size={14} className="text-primary-foreground" />
            </div>
            iCoDer
          </a>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setLocale(locale === 'zh-CN' ? 'en-US' : 'zh-CN')}
              className="text-xs px-2 py-1 rounded border border-border hover:bg-accent transition-colors font-medium"
            >
              {locale === 'zh-CN' ? 'EN' : '中'}
            </button>
            {/* Organization switcher */}
            <OrgSwitcher />
            {/* Theme toggle */}
            <ThemeToggle />
            {/* Notification dropdown */}
            <div className="relative">
              <button onClick={() => { setShowNotif(!showNotif); setShowUserMenu(false); }}
                className="p-2 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors relative">
                <Bell size={16} />
                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500" />
              </button>
              {showNotif && (
                <div className="absolute right-0 top-full mt-1 w-64 bg-popover border border-border rounded-xl shadow-lg z-50 overflow-hidden">
                  <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground">通知</span>
                  </div>
                  <div className="py-4 text-center text-xs text-muted-foreground">
                    暂无新通知
                  </div>
                  <div className="px-4 py-2 border-t border-border bg-muted/30">
                    <button onClick={() => { navigate('/support'); setShowNotif(false); }}
                      className="text-xs text-primary hover:underline w-full text-left">查看帮助</button>
                  </div>
                </div>
              )}
            </div>
            {/* User menu dropdown */}
            <div className="relative">
              <button onClick={() => { setShowUserMenu(!showUserMenu); setShowNotif(false); }}
                className="flex items-center gap-2 rounded-md p-1.5 text-sm hover:bg-accent transition-colors">
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-xs font-medium text-primary-foreground shrink-0">
                  {initials}
                </div>
              </button>
              {showUserMenu && (
                <div className="absolute right-0 top-full mt-1 w-48 bg-popover border border-border rounded-xl shadow-lg z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-border">
                    <p className="text-sm font-medium text-foreground truncate">{user?.full_name || '用户'}</p>
                    <p className="text-[10px] text-muted-foreground truncate">{user?.email || ''}</p>
                  </div>
                  <div className="py-1">
                    <button onClick={() => { navigate('/settings'); setShowUserMenu(false); }}
                      className="w-full text-left px-4 py-2 text-xs text-foreground hover:bg-accent transition-colors flex items-center gap-2">
                      <Settings size={12} /> {t.settings}
                    </button>
                    <button onClick={() => { navigate('/billing'); setShowUserMenu(false); }}
                      className="w-full text-left px-4 py-2 text-xs text-foreground hover:bg-accent transition-colors flex items-center gap-2">
                      <CreditCard size={12} /> {t.billing}
                    </button>
                    <button onClick={() => { logout(); setShowUserMenu(false); }}
                      className="w-full text-left px-4 py-2 text-xs text-red-500 hover:bg-red-50 transition-colors flex items-center gap-2">
                      <ChevronDown size={12} className="rotate-180" /> 退出登录
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* ====== Body: Sidebar + Main ====== */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <aside className={`flex flex-col border-r border-sidebar-border bg-sidebar transition-all duration-200 shrink-0 ${collapsed ? 'w-[48px]' : 'w-[224px]'}`}>
          {/* Sidebar header: project selector + toggle */}
          <div className="flex items-center gap-2 px-2 py-2 border-b border-sidebar-border">
            {!collapsed ? (
              <>
                <div className="relative flex-1">
                  <button onClick={() => setShowProjectMenu(!showProjectMenu)}
                    className="flex items-center gap-2 mx-2 w-[calc(100%-16px)] h-[48px] cursor-pointer rounded-lg px-2 py-1.5 hover:bg-sidebar-accent transition-colors">
                    <Folder size={18} className="text-sidebar-foreground shrink-0" />
                    <div className="flex-1 min-w-0 text-left">
                      {editingProjectName ? (
                        <input
                          value={projectName}
                          onChange={e => setProjectName(e.target.value)}
                          onBlur={() => { saveProjectName(projectName); setEditingProjectName(false); }}
                          onKeyDown={e => { if (e.key === 'Enter') { saveProjectName(projectName); setEditingProjectName(false); } }}
                          className="w-full text-sm font-semibold bg-sidebar-accent border border-border rounded px-1.5 py-0.5 text-sidebar-foreground outline-none"
                          autoFocus
                          onClick={e => e.stopPropagation()}
                        />
                      ) : (
                        <p
                          className="truncate font-semibold text-sm text-sidebar-foreground cursor-text hover:bg-sidebar-accent/50 rounded px-1.5 py-0.5 -mx-1.5"
                          onDoubleClick={(e) => { e.stopPropagation(); setEditingProjectName(true); }}
                          title="Double-click to rename"
                        >
                          {projectName}
                        </p>
                      )}
                      <p className="truncate text-xs text-muted-foreground">{selectedClient}</p>
                    </div>
                    <ChevronsUpDown size={14} className="text-muted-foreground shrink-0" />
                  </button>
                  {showProjectMenu && (
                    <div className="absolute left-2 top-full mt-1 w-52 bg-popover border border-border rounded-xl shadow-lg z-50 overflow-hidden">
                      <div className="px-3 py-2 border-b border-border">
                        <p className="text-[10px] text-muted-foreground">{t.apiClients}</p>
                      </div>
                      <div className="max-h-40 overflow-y-auto py-1">
                        <button onClick={() => { setSelectedClient(PROJECT_SLUG); setShowProjectMenu(false); }}
                          className={`w-full text-left px-3 py-2 text-xs transition-colors ${selectedClient === PROJECT_SLUG ? 'bg-primary/5 text-primary' : 'text-foreground hover:bg-accent'}`}>
                          {PROJECT_SLUG} {t.defaultLabel}
                        </button>
                        {apiClients.map((c: any) => (
                          <button key={c.client_id} onClick={() => { setSelectedClient(c.client_id); setShowProjectMenu(false); }}
                            className={`w-full text-left px-3 py-2 text-xs transition-colors ${selectedClient === c.client_id ? 'bg-primary/5 text-primary' : 'text-foreground hover:bg-accent'}`}>
                            {c.name}
                          </button>
                        ))}
                      </div>
                      <div className="px-3 py-2 border-t border-border bg-muted/30">
                        <button onClick={() => { navigate('/api-clients'); setShowProjectMenu(false); }}
                          className="text-[10px] text-primary hover:underline w-full text-left">{t.apiClientsManage}</button>
                      </div>
                    </div>
                  )}
                </div>
                <button onClick={() => setCollapsed(true)}
                  className="p-1.5 rounded-md text-sidebar-foreground hover:bg-sidebar-accent shrink-0 transition-colors"
                  title={t.toggleSidebar}>
                  <PanelLeftClose size={16} />
                </button>
              </>
            ) : (
              <button onClick={() => setCollapsed(false)}
                className="p-1.5 rounded-md text-sidebar-foreground hover:bg-sidebar-accent mx-auto transition-colors"
                title={t.toggleSidebar}>
                <PanelLeft size={16} />
              </button>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-2">
            {/* Top items (Home, Developer quickstart) — no group label */}
            {(!collapsed || true) && topItems.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end}
                className={({ isActive }) =>
                  `sidebar-item ${isActive ? 'active' : ''} ${collapsed ? 'justify-center px-1' : 'px-2 mx-2'}`
                }
                title={collapsed ? item.label : undefined}>
                <item.icon size={16} />
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            ))}

            {/* Section groups */}
            {navSections.map((section) => (
              <div key={section.name} className="mt-2">
                {!collapsed && (
                  <div className="sidebar-section-header px-2 mx-2">{section.name}</div>
                )}
                {section.items.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.end}
                    className={({ isActive }) =>
                      `sidebar-item ${isActive ? 'active' : ''} ${collapsed ? 'justify-center px-1' : 'px-2 mx-2'}`
                    }
                    title={collapsed ? item.label : undefined}>
                    <item.icon size={16} />
                    {!collapsed && <span className="flex-1">{item.label}</span>}
                    {(item as any).external && !collapsed && (
                      <ArrowUpRight size={12} className="text-muted-foreground shrink-0" />
                    )}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          {/* Sidebar footer: user */}
          <div className="border-t border-sidebar-border p-2">
            {!collapsed && user && (
              <div className="flex items-center gap-2 rounded-md p-2 h-12">
                <div className="w-8 h-8 rounded-md bg-muted flex items-center justify-center text-xs font-medium text-foreground shrink-0">
                  {initials}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-sidebar-foreground truncate">{user.full_name}</p>
                  <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                </div>
                <ChevronsUpDown size={14} className="text-muted-foreground shrink-0" />
              </div>
            )}
            {collapsed && (
              <div className="flex justify-center">
                <div className="w-8 h-8 rounded-md bg-muted flex items-center justify-center text-xs font-medium">
                  {initials}
                </div>
              </div>
            )}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-h-0 overflow-y-auto bg-background flex flex-col">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
