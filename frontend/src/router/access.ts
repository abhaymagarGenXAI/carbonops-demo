/** The built-in Administrator role (locked on the server: it always holds every permission). */
export const ADMIN_ROLE_ID = "R-AD";

/**
 * Single source of truth for "who may open which route".
 * Used by the route guards AND the sidebar, so the menu and the URL bar can never disagree.
 *
 * Access follows the PERMISSIONS of the active role (managed by the Administrator in Users & Access), not the role's name:
 * a route opens when the role holds ANY of the listed permissions. An empty list means every signed-in user.
 * (The API enforces its own permissions server-side.)
 */
export const ROUTE_PERMISSIONS: Record<string, readonly string[]> = {
  "/": [],
  "/assets": [],
  "/activity": ["page.activity"],
  "/energy": ["page.energy"],
  "/carbon": ["page.carbon"],
  "/initiatives": ["page.initiatives"],
  "/approvals": ["page.approvals"],
  "/assistant": [],
  "/documents": ["page.documents"],
  "/users": ["user.manage"],
  "/db-model-test": ["db.tools"],
  "/db-crud-test": ["db.tools"],
};

/** The Administrator is a governance role: its own menu stays free of the operational modules (as it always was) and it
 *  opens them through "Simulate role". Every other role - built-in or custom - is purely permission-driven. */
const ADMIN_MENU_EXCLUDES = new Set(["/activity", "/energy", "/carbon", "/initiatives", "/approvals"]);

export function canAccess(path: string, roleId: string | null, permissions: readonly string[]): boolean {
  const needed = ROUTE_PERMISSIONS[path];
  if (needed === undefined) return false;
  if (roleId === ADMIN_ROLE_ID && ADMIN_MENU_EXCLUDES.has(path)) return false;
  return needed.length === 0 || needed.some((code) => permissions.includes(code));
}
