// iCoDer - Zustand Store (Multi-Tenant)
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, Review, Encounter } from '../types';

export interface OrgInfo {
  id: string;
  name: string;
  slug: string;
  plan: string;
  role: string;
  is_default: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  organizations: OrgInfo[];
  currentOrgId: string | null;
  login: (user: User, accessToken: string, refreshToken: string, orgs?: OrgInfo[], orgId?: string) => void;
  setOrganizations: (orgs: OrgInfo[], orgId: string) => void;
  setCurrentOrgId: (orgId: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      organizations: [],
      currentOrgId: null,
      login: (user, accessToken, refreshToken, orgs = [], orgId = '') => {
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);
        set({ user, accessToken, refreshToken, isAuthenticated: true, organizations: orgs, currentOrgId: orgId });
      },
      setOrganizations: (orgs, orgId) => set({ organizations: orgs, currentOrgId: orgId }),
      setCurrentOrgId: (orgId) => set({ currentOrgId: orgId }),
      logout: () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, organizations: [], currentOrgId: null });
      },
    }),
    {
      name: 'icoder-auth',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
        organizations: state.organizations,
        currentOrgId: state.currentOrgId,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.accessToken) {
          localStorage.setItem('access_token', state.accessToken);
          localStorage.setItem('refresh_token', state.refreshToken || '');
        }
      },
    },
  ),
);

interface AppState {
  sidebarCollapsed: boolean;
  currentReview: Review | null;
  currentEncounter: Encounter | null;
  processing: boolean;
  error: string | null;
  toggleSidebar: () => void;
  setCurrentReview: (review: Review | null) => void;
  setCurrentEncounter: (encounter: Encounter | null) => void;
  setProcessing: (v: boolean) => void;
  setError: (e: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  currentReview: null,
  currentEncounter: null,
  processing: false,
  error: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setCurrentReview: (review) => set({ currentReview: review }),
  setCurrentEncounter: (encounter) => set({ currentEncounter: encounter }),
  setProcessing: (v) => set({ processing: v }),
  setError: (e) => set({ error: e }),
}));

// Live cost tracker — iCoDer-style $X.XXXXXX per-session counter
interface CostState {
  liveCost: number;
  addCost: (amount: number) => void;
  resetCost: () => void;
}

export const useCostStore = create<CostState>((set) => ({
  liveCost: 0,
  addCost: (amount) => set((s) => ({ liveCost: s.liveCost + amount })),
  resetCost: () => set({ liveCost: 0 }),
}));

// Dark/light theme
type Theme = 'light' | 'dark';
interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
}
const getInitialTheme = (): Theme => {
  const stored = localStorage.getItem('icoder-theme');
  if (stored === 'dark' || stored === 'light') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};
const applyTheme = (theme: Theme) => {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  localStorage.setItem('icoder-theme', theme);
};
applyTheme(getInitialTheme());

export const useThemeStore = create<ThemeState>((set) => ({
  theme: getInitialTheme(),
  toggleTheme: () => set((s) => {
    const next = s.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    return { theme: next };
  }),
}));

// Toast notification system
export interface Toast {
  id: string;
  message: string;
  type: 'error' | 'warning' | 'success';
}

interface ToastState {
  toasts: Toast[];
  addToast: (message: string, type: Toast['type']) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (message, type) => {
    const id = Math.random().toString(36).slice(2, 8);
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 5000);
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
