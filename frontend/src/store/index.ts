// iCoDer - Zustand Store (Multi-Tenant)
import { create } from 'zustand';

import type { User, Review, Encounter } from '../types';

// ── Phase A1A Gate 4.6 — browser storage PHI boundary ─────────────
//
// Canonical list of every localStorage key the frontend writes.
// ``clearAllIcoderBrowserStorage`` wipes all of them on logout so a
// shared machine does not retain the previous user's templates /
// preferences / auth state.
//
// NOTE: add new keys here when introducing new localStorage writes.
// The unit test in tests/browser/storage-audit.test.ts (TODO) gates
// this list against the source-of-truth grep.
const ICODER_LOCALSTORAGE_KEYS = [
  'access_token',
  'refresh_token',
  'icoder-auth',
  'icoder-textgen-templates',
  'icoder-project-name',
  'icoder-billing-alerts',
  'icoder-billing-autotopup',
  'icoder-settings',
  'icoder-agent-runtime-mode',
  'icoder-theme',
];

export function clearAllIcoderBrowserStorage(): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  for (const key of ICODER_LOCALSTORAGE_KEYS) {
    try { window.localStorage.removeItem(key); } catch { /* ignore */ }
  }
  try {
    for (const key of Object.keys(window.sessionStorage)) {
      if (key.startsWith('icoder-context:')) window.sessionStorage.removeItem(key);
    }
  } catch { /* browser storage may be unavailable */ }
}

export function listIcoderBrowserStorageKeys(): string[] {
  if (typeof window === 'undefined' || !window.localStorage) return [];
  return ICODER_LOCALSTORAGE_KEYS.filter(k => {
    try { return window.localStorage.getItem(k) !== null; } catch { return false; }
  });
}

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

// Retire legacy persisted credentials on first load. Browser sessions are restored
// from the HttpOnly cookie; no JWT or user profile is rehydrated from storage.
if(typeof localStorage!=='undefined')for(const key of ['access_token','refresh_token','icoder-auth'])localStorage.removeItem(key);
export const useAuthStore = create<AuthState>()((set,get)=>({
 user:null,accessToken:null,refreshToken:null,isAuthenticated:false,organizations:[],currentOrgId:null,
 login:(user,accessToken,_refreshToken,organizations=[],currentOrgId='')=>{
  for(const key of ['access_token','refresh_token','icoder-auth'])localStorage.removeItem(key);
  set({user,accessToken,refreshToken:null,isAuthenticated:true,organizations,currentOrgId});
 },
 setOrganizations:(organizations,currentOrgId)=>set({organizations,currentOrgId}),
 setCurrentOrgId:currentOrgId=>set({currentOrgId}),
 logout:()=>{
  void fetch('/api/auth/browser/logout',{method:'POST',credentials:'same-origin',headers:{'X-iCoDer-Browser':'1'}}).then(async r=>{
   if(!r.ok)throw Error();
   const session=await import('../services/browserSession');session.invalidateBrowserSession();
   clearAllIcoderBrowserStorage();
   set({user:null,accessToken:null,refreshToken:null,isAuthenticated:false,organizations:[],currentOrgId:null});
  }).catch(()=>useToastStore.getState().addToast('退出未确认，请检查网络后重试。','error'));
 }
}));

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

// Live cost tracker — ¥X.XXXXXX per-session counter.
// sessionStartBalance = balance at session start (or last reset).
// After each A2A run, syncFromBalance(currentBalance) computes the delta
// (sessionStartBalance - currentBalance) and sets liveCost to it.
// resetCost() sets sessionStartBalance to the latest known balance so liveCost→0.
interface CostState {
  liveCost: number;
  sessionStartBalance: number | null;
  addCost: (amount: number) => void;
  resetCost: () => void;
  setSessionStartBalance: (balance: number) => void;
  syncFromBalance: (currentBalance: number) => void;
}

export const useCostStore = create<CostState>((set) => ({
  liveCost: 0,
  sessionStartBalance: null,
  addCost: (amount) => set((s) => ({ liveCost: s.liveCost + amount })),
  resetCost: () => set({ liveCost: 0, sessionStartBalance: null }),
  setSessionStartBalance: (balance) => set({ sessionStartBalance: balance, liveCost: 0 }),
  syncFromBalance: (currentBalance) => set((s) => {
    if (s.sessionStartBalance === null) {
      // First sync — establish baseline, no cost yet
      return { sessionStartBalance: currentBalance, liveCost: 0 };
    }
    const delta = s.sessionStartBalance - currentBalance;
    return { liveCost: delta > 0 ? delta : 0 };
  }),
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
