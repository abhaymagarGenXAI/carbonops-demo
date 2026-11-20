import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";
import { AppSidebar } from "@/components/app-sidebar";
import { TopBar } from "@/components/top-bar";
import { SidebarProvider } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { StoreProvider, useStore } from "@/lib/store";
import { FullPageSpinner } from "@/router/guards";

/** Holds the page back until the first server data has arrived (pages assume non-empty reference lists). */
function WorkspaceGate({ children }: { children: ReactNode }) {
  const { isLoading, error, reload } = useStore();
  if (isLoading) return <FullPageSpinner label="Loading workspace…" />;
  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="max-w-md space-y-3 text-center">
          <h1 className="text-xl font-semibold">Couldn't load the workspace</h1>
          <p className="text-sm text-muted-foreground">{error.message}</p>
          <Button onClick={reload}>Retry</Button>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

/** Authenticated shell: sidebar + top bar + routed page. (Was RootComponent in __root.tsx.) */
export default function AppLayout() {
  return (
    <StoreProvider>
      <WorkspaceGate>
        <SidebarProvider>
          <div className="flex min-h-screen w-full bg-background">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <TopBar />
              <main className="flex-1 px-4 py-6 lg:px-8">
                <Outlet />
              </main>
            </div>
          </div>
        </SidebarProvider>
      </WorkspaceGate>
    </StoreProvider>
  );
}
