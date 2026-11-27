import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import { ApiError } from "@/services/api";
import { router } from "@/router";
import { ErrorBoundary } from "@/components/error-boundary";
import "./styles.css";

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => console.error("[query]", error),
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // don't hammer the API on 4xx (auth/validation/not-found); retry transient failures twice
      retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ErrorBoundary>
          <RouterProvider router={router} />
        </ErrorBoundary>
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
