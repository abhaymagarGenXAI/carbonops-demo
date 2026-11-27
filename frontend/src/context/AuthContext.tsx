import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, registerAuthFailureHandler } from "@/services/api";
import { useRoles } from "@/hooks/useApi";
import { ADMIN_ROLE_ID, canAccess } from "@/router/access";
import type { AppRole, UserRec } from "@/types/domain";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthValue {
  user: UserRec | null;
  status: AuthStatus;
  /** Role the UI currently behaves as. Equals user.appRole unless an Administrator is "viewing as" another role. */
  role: AppRole;
  /** Id of that role (null until the user is known). */
  roleId: string | null;
  /** Permission codes of the role the UI currently behaves as. */
  permissions: readonly string[];
  /** Does the role the UI behaves as hold this permission? Use for showing/hiding actions. */
  can: (code: string) => boolean;
  /** Does the REAL signed-in user hold this permission (ignores "Simulate role")? Mirrors what the API will allow. */
  hasPermission: (code: string) => boolean;
  /** May the role the UI behaves as open this route? */
  canOpen: (path: string) => boolean;
  /** UI-only "Simulate role" preview — offered to real Administrators only; the API always enforces the real role. */
  canSimulateRole: boolean;
  /** Preview the app as another role (by id). */
  setRole: (roleId: string) => void;
  login: (email: string, password: string) => Promise<UserRec>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserRec | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [simulatedId, setSimulatedId] = useState<string | null>(null);
  const canSimulateRole = !!user && (user.roleId === ADMIN_ROLE_ID || user.appRole === "Administrator");
  const { data: roles = [] } = useRoles(canSimulateRole);

  const clearSession = useCallback(() => {
    queryClient.clear(); // never leak one user's cached data to the next
    setUser(null);
    setSimulatedId(null);
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

  // Role/permission edits made by an Administrator reach people who are already signed in: re-read "me" every minute and
  // whenever the tab regains focus (the API itself enforces changes on the very next request).
  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = () => {
      void authApi
        .me()
        .then((fresh) => setUser((prev) => (prev && JSON.stringify(prev) === JSON.stringify(fresh) ? prev : fresh)))
        .catch(() => undefined); // a real 401 is handled by the shared auth-failure handler
    };
    const timer = window.setInterval(refresh, 60_000);
    const onVisible = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [status]);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await authApi.login(email, password);
      queryClient.clear();
      setSimulatedId(null);
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
    const simulatedRole = canSimulateRole && simulatedId ? roles.find((r) => r.id === simulatedId) ?? null : null;
    const realPermissions = user?.permissions ?? [];
    const permissions = simulatedRole ? simulatedRole.permissions : realPermissions;
    const roleId = simulatedRole ? simulatedRole.id : user?.roleId ?? null;
    return {
      user,
      status,
      role: simulatedRole ? simulatedRole.name : user?.appRole ?? "",
      roleId,
      permissions,
      can: (code) => permissions.includes(code),
      hasPermission: (code) => realPermissions.includes(code),
      canOpen: (path) => canAccess(path, roleId, permissions),
      canSimulateRole,
      setRole: (id) => {
        if (canSimulateRole) setSimulatedId(id);
      },
      login,
      logout,
    };
  }, [user, status, simulatedId, roles, canSimulateRole, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
