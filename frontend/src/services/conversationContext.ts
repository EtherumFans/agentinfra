// Persist only a context reference, never medical text, scoped to actor and tenant.
export const contextKey = (user: string, org: string, agent: string) =>
  `icoder-context:${encodeURIComponent(user)}:${encodeURIComponent(org)}:${encodeURIComponent(agent)}`;
export function readContext(key: string): string {
  try { return sessionStorage.getItem(key) || ''; } catch { return ''; }
}
export function saveContext(key: string, id: string) {
  try { if (id) sessionStorage.setItem(key, id); else sessionStorage.removeItem(key); } catch { /* optional browser persistence */ }
}
