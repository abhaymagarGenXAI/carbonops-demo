import { useState } from "react";
import { KeyRound, Lock, Pencil, Plus, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DataTable, type Column } from "@/components/data-table";
import { BulkConfirm } from "@/components/bulk-confirm";
import { runBulk } from "@/lib/bulk";
import { PageHeader, SectionCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { useAuth } from "@/context/AuthContext";
import {
  useCreateRole, useCreateUser, useDeleteRole, useDeleteUser, usePermissions, useResetUserPassword, useRoles,
  useSetRolePermissions, useSetUserAccess, useSetUserStatus, useUpdateRole, useUpdateUser,
} from "@/hooks/useApi";
import { useStore } from "@/lib/store";
import type { PermissionRec, RoleRec, UserChanges, UserRec } from "@/types/domain";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Unexpected error");
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MIN_PASSWORD = 12;

const MODULE_LABEL: Record<string, string> = {
  access: "Page access (menu & pages)",
  activity: "Activity data",
  approvals: "Approvals",
  energy: "Energy",
  carbon: "Carbon accounting",
  governance: "Governance",
  initiatives: "Initiatives",
  master: "Master data",
  admin: "Administration",
};
const moduleLabel = (m: string) => MODULE_LABEL[m] ?? m;

/** A random 16-character password the administrator can hand to the user. */
function generatePassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*?";
  const buf = new Uint32Array(16);
  crypto.getRandomValues(buf);
  return Array.from(buf, (n) => chars[n % chars.length]).join("");
}

/* ---------------------------------------------------------------- add / edit user */
function UserDialog({ target, onClose }: { target: UserRec | "new"; onClose: () => void }) {
  const user: UserRec | null = target === "new" ? null : target;
  const isNew = user === null;
  const { allFacilities: facilities } = useStore();
  const { user: me } = useAuth();
  const { data: roles = [] } = useRoles(true);
  const create = useCreateUser(), update = useUpdateUser(), setAccess = useSetUserAccess();
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [title, setTitle] = useState(user?.role ?? "");
  const [roleId, setRoleId] = useState(user?.roleId ?? roles.find((r) => r.name === user?.appRole)?.id ?? roles.find((r) => r.name === "Plant Engineer")?.id ?? "");
  const [facIds, setFacIds] = useState<string[]>(user?.facilityIds ?? []);
  const [password, setPassword] = useState("");
  const isSelf = !!user && user.id === me?.id;
  const busy = create.isPending || update.isPending || setAccess.isPending;
  const toggle = (id: string) => setFacIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const problem = !name.trim() ? "Enter the user’s name."
    : !EMAIL.test(email.trim()) ? "Enter a valid e-mail address."
    : !title.trim() ? "Enter a job title."
    : !roleId ? "Choose a role."
    : isNew && password.length < MIN_PASSWORD ? `The password needs at least ${MIN_PASSWORD} characters.`
    : "";

  const save = async () => {
    if (problem) {
      toast.error("Cannot save yet", { description: problem });
      return;
    }
    try {
      if (user === null) {
        const created = await create.mutateAsync({ name: name.trim(), email: email.trim(), role: title.trim(), roleId, facilityIds: facIds, password });
        toast.success(`${created.name} added`, { description: `They can sign in now as ${created.appRole}.` });
      } else {
        const changes: UserChanges = {};
        if (name.trim() !== user.name) changes.name = name.trim();
        if (email.trim().toLowerCase() !== user.email) changes.email = email.trim();
        if (title.trim() !== user.role) changes.role = title.trim();
        if (Object.keys(changes).length) await update.mutateAsync({ id: user.id, changes });
        await setAccess.mutateAsync({ id: user.id, roleId, facilityIds: facIds });
        toast.success(`${name.trim()} updated`, { description: "Role changes apply on their next request." });
      }
      onClose();
    } catch (e) {
      toast.error(isNew ? "Could not add the user" : "Could not update the user", { description: msg(e) });
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isNew ? "Add user" : `Edit user — ${user?.name}`}</DialogTitle>
          <DialogDescription>
            {isNew ? "Create an account and choose its role. The user can sign in straight away." : "Change the user’s details, role and facilities. A new role applies on their next request."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="u-name">Full name</Label>
              <Input id="u-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="u-title">Job title</Label>
              <Input id="u-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Facility Engineer" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="u-email">E-mail (used to sign in)</Label>
            <Input id="u-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="u-role">Role</Label>
            <Select value={roleId} onValueChange={setRoleId} disabled={isSelf}>
              <SelectTrigger id="u-role" aria-label="Role"><SelectValue placeholder="Select a role" /></SelectTrigger>
              <SelectContent>{roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {isSelf ? "You cannot change your own role — ask another administrator." : roles.find((r) => r.id === roleId)?.description}
            </p>
          </div>
          {isNew ? (
            <div className="space-y-1.5">
              <Label htmlFor="u-pass">Initial password</Label>
              <div className="flex gap-2">
                <Input id="u-pass" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" placeholder={`At least ${MIN_PASSWORD} characters`} maxLength={72} />
                <Button type="button" variant="outline" onClick={() => setPassword(generatePassword())}>Generate</Button>
              </div>
              <p className="text-xs text-muted-foreground">Shown here so you can pass it on securely; it is stored hashed and cannot be read again.</p>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>Facilities</Label>
            <div className="grid max-h-40 gap-2 overflow-y-auto rounded-md border p-3">
              {facilities.map((f) => (
                <label key={f.id} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={facIds.includes(f.id)} onCheckedChange={() => toggle(f.id)} aria-label={f.name} /> {f.name} <span className="text-xs text-muted-foreground">{f.code}{f.active === false ? " · inactive" : ""}</span>
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Informational: leave all unticked for “All Facilities”. Every facility stays visible to every role.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy}>{isNew ? "Add user" : "Save changes"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- reset password */
function ResetPasswordDialog({ user, onClose }: { user: UserRec; onClose: () => void }) {
  const reset = useResetUserPassword();
  const [password, setPassword] = useState("");
  const save = async () => {
    if (password.length < MIN_PASSWORD) {
      toast.error("Password too short", { description: `Use at least ${MIN_PASSWORD} characters.` });
      return;
    }
    try {
      await reset.mutateAsync({ id: user.id, newPassword: password });
      toast.success(`Password reset for ${user.name}`, { description: "Their existing sessions were signed out." });
      onClose();
    } catch (e) {
      toast.error("Could not reset the password", { description: msg(e) });
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reset password — {user.name}</DialogTitle>
          <DialogDescription>Sets a new password and signs the user out everywhere. Pass the new password on securely.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="rp">New password</Label>
          <div className="flex gap-2">
            <Input id="rp" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" placeholder={`At least ${MIN_PASSWORD} characters`} maxLength={72} />
            <Button type="button" variant="outline" onClick={() => setPassword(generatePassword())}>Generate</Button>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={reset.isPending}>Reset password</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- create / edit role */
function RoleDialog({ target, permissions, onClose }: { target: RoleRec | "new"; permissions: PermissionRec[]; onClose: () => void }) {
  const role: RoleRec | null = target === "new" ? null : target;
  const isNew = role === null;
  const locked = !!role?.isLocked;
  const create = useCreateRole(), update = useUpdateRole(), setPerms = useSetRolePermissions();
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected, setSelected] = useState<string[]>(role?.permissions ?? []);
  const modules = [...new Set(permissions.map((p) => p.module))];
  const busy = create.isPending || update.isPending || setPerms.isPending;
  const toggle = (code: string) => setSelected((p) => (p.includes(code) ? p.filter((c) => c !== code) : [...p, code]));
  const toggleModule = (m: string) => {
    const codes = permissions.filter((p) => p.module === m).map((p) => p.code);
    setSelected((p) => (codes.every((c) => p.includes(c)) ? p.filter((c) => !codes.includes(c)) : [...new Set([...p, ...codes])]));
  };

  const save = async () => {
    if (name.trim().length < 2) {
      toast.error("Cannot save yet", { description: "Give the role a name (at least 2 characters)." });
      return;
    }
    try {
      if (role === null) {
        const created = await create.mutateAsync({ name: name.trim(), description: description.trim(), permissions: selected });
        toast.success(`Role “${created.name}” created`, { description: `${created.permissions.length} permissions granted.` });
      } else {
        const changes: { name?: string; description?: string } = {};
        if (!role.isSystem && name.trim() !== role.name) changes.name = name.trim();
        if (description.trim() !== role.description) changes.description = description.trim();
        if (Object.keys(changes).length) await update.mutateAsync({ id: role.id, changes });
        const same = selected.length === role.permissions.length && selected.every((c) => role.permissions.includes(c));
        if (!same) await setPerms.mutateAsync({ id: role.id, permissions: selected });
        toast.success(`Role “${role.name}” updated`, { description: "Changes apply to its members immediately." });
      }
      onClose();
    } catch (e) {
      toast.error(isNew ? "Could not create the role" : "Could not update the role", { description: msg(e) });
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isNew ? "New role" : locked ? `Role — ${role?.name}` : `Edit role — ${role?.name}`}</DialogTitle>
          <DialogDescription>
            {locked
              ? "The Administrator role always holds every permission, so the system can never be locked out. It cannot be edited or deleted."
              : "Choose exactly what members of this role can see and do. Changes apply to everyone holding the role on their next request."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="r-name">Role name</Label>
              <Input id="r-name" value={name} onChange={(e) => setName(e.target.value)} disabled={locked || !!role?.isSystem} maxLength={60} />
              {role?.isSystem ? <p className="text-xs text-muted-foreground">Built-in roles keep their name.</p> : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-desc">Description</Label>
              <Textarea id="r-desc" value={description} onChange={(e) => setDescription(e.target.value)} disabled={locked} rows={2} maxLength={240} />
            </div>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>Permissions</Label>
              <span className="text-xs text-muted-foreground">{locked ? permissions.length : selected.length} of {permissions.length} granted</span>
            </div>
            {modules.map((m) => {
              const items = permissions.filter((p) => p.module === m);
              const allOn = items.every((p) => locked || selected.includes(p.code));
              return (
                <div key={m} className="rounded-md border">
                  <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide">{moduleLabel(m)}</span>
                    {locked ? null : <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => toggleModule(m)}>{allOn ? "Clear all" : "Select all"}</Button>}
                  </div>
                  <div className="divide-y">
                    {items.map((p) => (
                      <label key={p.code} className="flex items-start gap-3 px-3 py-2 text-sm">
                        <Checkbox className="mt-0.5" checked={locked || selected.includes(p.code)} disabled={locked} onCheckedChange={() => toggle(p.code)} aria-label={p.code} />
                        <span><code className="text-xs">{p.code}</code><span className="block text-xs text-muted-foreground">{p.description}</span></span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
            {!locked && selected.includes("user.manage") ? (
              <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs">
                <strong>user.manage</strong> lets members add, edit and delete users and change every role’s permissions. Grant it only to people you trust as administrators.
              </p>
            ) : null}
            <p className="text-xs text-muted-foreground">“Page access” permissions decide which pages appear in a user’s menu; the other permissions decide which actions the server allows.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{locked ? "Close" : "Cancel"}</Button>
          {locked ? null : <Button onClick={save} disabled={busy}>{isNew ? "Create role" : "Save role"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Administrator screen: add / edit / remove users, choose each user's role, and manage roles and their permissions.
 *  Facility assignments are stored for reference; every facility stays visible to every role (no facility scoping).
 *  Role and permission changes apply on the affected users' next request. */
export default function UsersPage() {
  const { users, facilities } = useStore();
  const { user: me } = useAuth();
  const { data: roles = [] } = useRoles(true);
  const { data: permissions = [] } = usePermissions(true);
  const setStatus = useSetUserStatus(), removeUser = useDeleteUser(), removeRole = useDeleteRole();
  const [userDialog, setUserDialog] = useState<UserRec | "new" | null>(null);
  const [passwordFor, setPasswordFor] = useState<UserRec | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserRec | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<"delete" | "suspend" | "activate" | null>(null);
  const [roleDialog, setRoleDialog] = useState<RoleRec | "new" | null>(null);
  const [deleteRole, setDeleteRole] = useState<RoleRec | null>(null);

  const facName = (id: string) => facilities.find((f) => f.id === id)?.name ?? id;
  const toggleStatus = (u: UserRec) =>
    setStatus.mutateAsync({ id: u.id, status: u.status === "Active" ? "Suspended" : "Active" })
      .then(() => toast.success(`${u.name} is now ${u.status === "Active" ? "suspended" : "active"}`))
      .catch((e: unknown) => toast.error("Could not change status", { description: msg(e) }));

  const confirmDeleteUser = async () => {
    if (!deleteUser) return;
    try {
      await removeUser.mutateAsync(deleteUser.id);
      toast.success(`${deleteUser.name} was removed`);
      setDeleteUser(null);
    } catch (e) {
      toast.error("Could not delete the user", { description: msg(e) });
    }
  };
  const confirmDeleteRole = async () => {
    if (!deleteRole) return;
    try {
      await removeRole.mutateAsync(deleteRole.id);
      toast.success(`Role “${deleteRole.name}” deleted`);
      setDeleteRole(null);
    } catch (e) {
      toast.error("Could not delete the role", { description: msg(e) });
    }
  };

  const columns: Column<UserRec>[] = [
    { key: "name", header: "User", sortable: true, value: (u) => u.name, render: (u) => <span>{u.name}<span className="block text-xs text-muted-foreground">{u.email}</span></span> },
    { key: "title", header: "Job title", value: (u) => u.role },
    { key: "role", header: "Role", sortable: true, value: (u) => u.appRole, render: (u) => <Badge variant="secondary">{u.appRole}</Badge> },
    { key: "fac", header: "Assigned facilities", value: (u) => u.facility,
      render: (u) => u.facilityIds.length ? <div className="flex flex-wrap gap-1">{u.facilityIds.map((f) => <Badge key={f} variant="outline">{facName(f)}</Badge>)}</div> : <span className="text-xs text-muted-foreground">None assigned (all visible)</span> },
    { key: "status", header: "Status", value: (u) => u.status, render: (u) => <StatusBadge value={u.status} /> },
    { key: "actions", header: "", render: (u) => (
      <div className="flex flex-wrap justify-end gap-1">
        <Button size="sm" variant="outline" onClick={() => setUserDialog(u)}><Pencil className="size-4" /> Edit</Button>
        <Button size="sm" variant="outline" title="Reset password" aria-label={`Reset password for ${u.name}`} onClick={() => setPasswordFor(u)}><KeyRound className="size-4" /></Button>
        <Button size="sm" variant="ghost" disabled={u.id === me?.id} onClick={() => toggleStatus(u)}>{u.status === "Active" ? "Suspend" : "Reactivate"}</Button>
        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" disabled={u.id === me?.id} title={u.id === me?.id ? "You cannot delete your own account" : "Delete user"} aria-label={`Delete ${u.name}`} onClick={() => setDeleteUser(u)}><Trash2 className="size-4" /></Button>
      </div>) },
  ];

  const modules = [...new Set(permissions.map((p) => p.module))];
  return (
    <div className="space-y-6">
      <PageHeader title="Users & Access" breadcrumb="Governance" description="Add, edit and remove users, give each one a role, and decide exactly what every role may see and do. Changes apply on the affected users’ next request. Facility assignments are recorded for reference — all facilities remain visible to every role." />
      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="roles">Roles & permissions</TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="mt-4">
          <DataTable data={users} columns={columns} rowKey={(u) => u.id} pageSize={10}
            selection={{
              selected: picked, onChange: setPicked, isSelectable: (u) => u.id !== me?.id, // never your own account
              actions: (
                <>
                  <Button size="sm" variant="outline" onClick={() => setBulk("suspend")}>Suspend</Button>
                  <Button size="sm" variant="outline" onClick={() => setBulk("activate")}>Reactivate</Button>
                  <Button size="sm" variant="outline" className="text-destructive" onClick={() => setBulk("delete")}><Trash2 className="size-4" /> Delete</Button>
                </>
              ),
            }}
            toolbar={<Button onClick={() => setUserDialog("new")}><UserPlus className="size-4" /> Add user</Button>}
            searchKeys={(u) => `${u.name} ${u.email} ${u.role} ${u.appRole} ${u.facility}`} searchPlaceholder="Search name, e-mail or role…" />
        </TabsContent>
        <TabsContent value="roles" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setRoleDialog("new")}><Plus className="size-4" /> New role</Button>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {roles.map((r) => (
              <SectionCard key={r.id} title={r.name} description={`${r.code} · ${r.members} user${r.members === 1 ? "" : "s"}`}>
                <p className="text-sm text-muted-foreground">{r.description || "No description."}</p>
                <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                  {r.isLocked ? <Lock className="size-3.5" /> : <ShieldCheck className="size-3.5" />}
                  {r.permissions.length} permissions{r.isLocked ? " · locked (always everything)" : r.isSystem ? " · built-in role" : " · custom role"}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setRoleDialog(r)}>
                    {r.isLocked ? <><ShieldCheck className="size-4" /> View</> : <><Pencil className="size-4" /> Edit role</>}
                  </Button>
                  {!r.isSystem ? (
                    <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setDeleteRole(r)}><Trash2 className="size-4" /> Delete</Button>
                  ) : null}
                </div>
              </SectionCard>
            ))}
          </div>
          <SectionCard title="Permission matrix" description="Every grant at a glance, enforced on every API call. Use “Edit role” on a role card to change what it holds.">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4">Permission</th>{roles.map((r) => <th key={r.id} className="px-3 py-2 text-center">{r.name}</th>)}
                </tr></thead>
                <tbody>
                  {modules.map((m) => [
                    <tr key={m} className="bg-muted/40"><td colSpan={roles.length + 1} className="px-1 py-1.5 text-xs font-semibold uppercase tracking-wide">{moduleLabel(m)}</td></tr>,
                    ...permissions.filter((p) => p.module === m).map((p) => (
                      <tr key={p.code} className="border-b last:border-0">
                        <td className="py-2 pr-4"><code className="text-xs">{p.code}</code><span className="block text-xs text-muted-foreground">{p.description}</span></td>
                        {roles.map((r) => <td key={r.id} className="px-3 py-2 text-center">{r.permissions.includes(p.code) ? <span aria-label="granted">✓</span> : <span className="text-muted-foreground" aria-label="not granted">–</span>}</td>)}
                      </tr>)),
                  ])}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </TabsContent>
      </Tabs>

      {userDialog ? <UserDialog key={userDialog === "new" ? "new" : userDialog.id} target={userDialog} onClose={() => setUserDialog(null)} /> : null}
      {passwordFor ? <ResetPasswordDialog key={passwordFor.id} user={passwordFor} onClose={() => setPasswordFor(null)} /> : null}
      {roleDialog ? <RoleDialog key={roleDialog === "new" ? "new" : roleDialog.id} target={roleDialog} permissions={permissions} onClose={() => setRoleDialog(null)} /> : null}

      <BulkConfirm
        open={bulk !== null} confirmLabel={bulk === "delete" ? "Delete" : bulk === "suspend" ? "Suspend" : "Reactivate"}
        title={`${bulk === "delete" ? "Delete" : bulk === "suspend" ? "Suspend" : "Reactivate"} ${picked.size} user(s)?`}
        description={bulk === "delete" ? "Their sign-in is removed. Names on historical records stay (the audit trail is never rewritten). Suspend instead if they may return." : bulk === "suspend" ? "Suspended users can no longer sign in." : "These users will be able to sign in again."}
        onCancel={() => setBulk(null)}
        onConfirm={async () => {
          const act = bulk;
          const { failed } = await runBulk([...picked], act === "delete" ? "user(s) deleted" : act === "suspend" ? "user(s) suspended" : "user(s) reactivated",
            (id) => (act === "delete" ? removeUser.mutateAsync(id) : setStatus.mutateAsync({ id, status: act === "suspend" ? "Suspended" : "Active" })));
          setPicked(new Set(failed.map((f) => f.id)));
          setBulk(null);
        }}
      />
      <AlertDialog open={!!deleteUser} onOpenChange={(o) => !o && setDeleteUser(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleteUser?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Their account is removed and they are signed out immediately. Records they created stay in the system under their name and the audit trail is kept.
              If they may come back, suspend the account instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={removeUser.isPending} onClick={(e) => { e.preventDefault(); void confirmDeleteUser(); }}>Delete user</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!deleteRole} onOpenChange={(o) => !o && setDeleteRole(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete the role “{deleteRole?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteRole && deleteRole.members > 0
                ? `${deleteRole.members} user${deleteRole.members === 1 ? " still holds" : "s still hold"} this role. Move them to another role first — it cannot be deleted while it has members.`
                : "The role and its permission grants are removed. This cannot be undone."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={removeRole.isPending || (deleteRole?.members ?? 0) > 0} onClick={(e) => { e.preventDefault(); void confirmDeleteRole(); }}>Delete role</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
