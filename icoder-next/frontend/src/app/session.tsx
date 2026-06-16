import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Role } from "../types";

// The host app owns auth — here we model that with a simple role-based demo token
// (`demo:<role>`), the same bearer the backend's require_auth expects. In a real
// hospital deployment this would be an SSO/HIS-issued short-lived token injected by
// the host; the slice keeps it switchable so the role-gated flows are demoable.
interface Session {
  role: Role;
  token: string;
  setRole: (r: Role) => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>("coder");
  const value = useMemo<Session>(() => ({ role, token: `demo:${role}`, setRole }), [role]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
