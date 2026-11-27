import { useEffect, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export function FullPageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background" role="status" aria-live="polite">
      <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
        <span className="size-8 animate-spin rounded-full border-2 border-border border-t-primary" />
        {label}
      </div>
    </div>
  );
}

/** Private-route wrapper: everything nested below requires a signed-in user. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageSpinner label="Restoring session…" />;
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

/** Login page guard: signed-in users are bounced to where they were going (or the dashboard). */
export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== "/login" ? from : "/"} replace />;
  }
  return <>{children}</>;
}

function Denied() {
  useEffect(() => {
    toast.error("Access restricted", { description: "Your role does not have access to that page." });
  }, []);
  return <Navigate to="/" replace />;
}

/** Route guard: renders the nested route only if the active role's permissions open this path (see access.ts). */
export function RoleRoute({ path }: { path: string }) {
  const { canOpen } = useAuth();
  return canOpen(path) ? <Outlet /> : <Denied />;
}
