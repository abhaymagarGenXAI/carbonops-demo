import type { ReactNode } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import AppLayout from "@/pages/AppLayout";
import ActivityPage from "@/pages/ActivityPage";
import ApprovalsPage from "@/pages/ApprovalsPage";
import AssetsPage from "@/pages/AssetsPage";
import CarbonPage from "@/pages/CarbonPage";
import DashboardPage from "@/pages/DashboardPage";
import DbCrudTestPage from "@/pages/DbCrudTestPage";
import DbModelTestPage from "@/pages/DbModelTestPage";
import DocumentsPage from "@/pages/DocumentsPage";
import EnergyPage from "@/pages/EnergyPage";
import InitiativesPage from "@/pages/InitiativesPage";
import AssistantPage from "@/pages/AssistantPage";
import UsersPage from "@/pages/UsersPage";
import LoginPage from "@/pages/LoginPage";
import NotFoundPage from "@/pages/NotFoundPage";
import RouteErrorPage from "@/pages/RouteErrorPage";
import { ProtectedRoute, PublicOnlyRoute, RoleRoute } from "./guards";

/** A path guarded by the permission map in access.ts. */
const guarded = (path: string, element: ReactNode): RouteObject => ({
  element: <RoleRoute path={path} />,
  children: [{ path: path.slice(1), element }],
});

export const router = createBrowserRouter([
  { path: "/login", element: <PublicOnlyRoute><LoginPage /></PublicOnlyRoute> },
  {
    element: <ProtectedRoute />, // 1) must be signed in
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <AppLayout />, // 2) shell: sidebar + top bar, data store
        children: [
          { index: true, element: <DashboardPage /> },
          guarded("/assets", <AssetsPage />), // 3) per-route permission guards
          guarded("/activity", <ActivityPage />),
          guarded("/energy", <EnergyPage />),
          guarded("/carbon", <CarbonPage />),
          guarded("/initiatives", <InitiativesPage />),
          guarded("/approvals", <ApprovalsPage />),
          guarded("/assistant", <AssistantPage />),
          guarded("/documents", <DocumentsPage />),
          guarded("/users", <UsersPage />),
          guarded("/db-model-test", <DbModelTestPage />),
          guarded("/db-crud-test", <DbCrudTestPage />),
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
