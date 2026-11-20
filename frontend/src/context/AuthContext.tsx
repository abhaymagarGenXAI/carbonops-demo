import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, registerAuthFailureHandler } from "@/services/api";
import type { AppRole, UserRec } from "@/types/domain";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthValue {
  user: UserRec | null;
  status: AuthStatus;
  /** Role the UI currently behaves as. Equals user.appRole unless an Administrator is "viewing as" another role. */
  role: AppRole;
  /** UI-only "Simulate role" preview — offered to real Administrators only; the API always enforces the real role. */
  canSimulateRole: boolean;
  setRole: (role: AppRole) => void;
  login: (email: string, password: string) => Promise<UserRec>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserRec | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [simulated, setSimulated] = useState<AppRole | null>(null);

  const clearSession = useCallback(() => {
    queryClient.clear(); // never leak one user's cached data to the next
    setUser(null);
    setSimulated(null);
    setStatus("unauthenticated");
  }, [queryClient]);

  // Page load: try to restore the session from the httpOnly refresh cookie.
  useEffect(() => {
    let alive = true;
    registerAuthFailureHandler(clearSession);
    void authApi.restore().then((session) => {
      if (!alive) return;
      if (session) {
        setUser(session.user);
        setStatus("authenticated");
      } else {
        setStatus("unauthenticated");
      }
    });
    return () => {
      alive = false;
      registerAuthFailureHandler(null);
    };
  }, [clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await authApi.login(email, password);
      queryClient.clear();
      setSimulated(null);
      setUser(session.user);
      setStatus("authenticated");
      return session.user;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    clearSession();
  }, [clearSession]);

  const value = useMemo<AuthValue>(() => {
    const real = user?.appRole ?? "Plant Engineer";
    const canSimulateRole = user?.appRole === "Administrator";
    return {
      user,
      status,
      role: canSimulateRole && simulated ? simulated : real,
      canSimulateRole,
      setRole: (r) => {
        if (canSimulateRole) setSimulated(r);
      },
      login,
      logout,
    };
  }, [user, status, simulated, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
