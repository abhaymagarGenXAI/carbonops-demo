import type { AppRole } from "@/types/domain";

const PE: AppRole = "Plant Engineer";
const SM: AppRole = "Sustainability Manager";
const ADMIN: AppRole = "Administrator";

/**
 * Single source of truth for "who may open which route".
 * Used by the route guards AND the sidebar, so the menu and the URL bar can never disagree.
 * (Same matrix the sidebar used before; the API enforces its own permissions server-side.)
 */
export const ROUTE_ACCESS: Record<string, readonly AppRole[]> = {
  "/": [PE, SM, ADMIN],
  "/assets": [PE, SM, ADMIN],
  "/activity": [PE],
  "/energy": [PE, SM],
  "/carbon": [SM],
  "/initiatives": [SM],
  "/approvals": [SM],
  "/db-model-test": [ADMIN],
  "/db-crud-test": [ADMIN],
};

export const canAccess = (path: string, role: AppRole) => ROUTE_ACCESS[path]?.includes(role) ?? false;
