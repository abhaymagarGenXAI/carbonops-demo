import { useNavigate } from "react-router-dom";
import { alertLink } from "@/lib/alerts";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bell,
  Check,
  CircleUser,
  Command,
  LogOut,
  FileStack,
  Moon,
  Search,
  Sun,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuth } from "@/context/AuthContext";
import { useStore } from "@/lib/store";
import type { AppRole } from "@/types/domain";

const navTargets = [
  { label: "Dashboard", to: "/" },
  { label: "Facilities & Assets", to: "/assets" },
  { label: "Activity Data Collection", to: "/activity" },
  { label: "Energy Management", to: "/energy" },
  { label: "Carbon Accounting", to: "/carbon" },
  { label: "Decarbonization Initiatives", to: "/initiatives" },
  { label: "Validation & Approvals", to: "/approvals" },
  { label: "Document Repository", to: "/documents" },
  { label: "AI Assistant", to: "/assistant" },
  { label: "Administration", to: "/admin" },
];

// const roleOptions = [
//   "Operations Data Entry",
//   "Facility Engineer",
//   "Sustainability Analyst",
//   "Reviewer / Approver",
//   "Administrator",
// ];

const roleOptions: AppRole[] = [
  "Plant Engineer",
  "Sustainability Manager",
  "Administrator",
];

export function TopBar() {
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const navigate = useNavigate();
  const { role, setRole, submissions, aiAlerts, facilities } = useStore();
  const { user, canSimulateRole, logout } = useAuth();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const pendingApprovals = submissions.filter((s) => s.status === "Submitted" || s.status === "Under Review");

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface/90 px-3 backdrop-blur">
      <SidebarTrigger className="shrink-0" />
      <div className="hidden text-sm text-muted-foreground sm:block">
        ONGC · Sustainability Operations
      </div>

      <button
        type="button"
        onClick={() => setOpen(true)}
        className="ml-auto flex h-9 w-full max-w-md items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground transition-colors hover:border-ring"
      >
        <Search className="size-4" />
        <span className="truncate">Search facilities, assets, submissions…</span>
        <kbd className="ml-auto hidden items-center gap-0.5 rounded border border-border px-1.5 py-0.5 text-[10px] sm:flex">
          <Command className="size-3" />K
        </kbd>
      </button>

      <Popover>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon" className="relative shrink-0" aria-label="Notifications">
            <Bell className="size-4" />
            {aiAlerts.length + pendingApprovals.length > 0 ? <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive" /> : null}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-96 p-0">
          <div className="border-b border-border px-4 py-3">
            <p className="text-sm font-semibold">Notification centre</p>
            <p className="text-xs text-muted-foreground">
              {aiAlerts.length} AI alerts · {pendingApprovals.length} items awaiting action
            </p>
          </div>
          <div className="max-h-80 divide-y divide-border overflow-y-auto">
            {aiAlerts.map((a) => (
              <button key={a.id} type="button" className="flex w-full gap-3 px-4 py-3 text-left hover:bg-muted/50" onClick={() => navigate(alertLink(a, role))}>
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
                <div className="space-y-1">
                  <p className="text-sm font-medium">{a.title}</p>
                  <p className="text-xs text-muted-foreground">{a.detail}</p>
                </div>
              </button>
            ))}
            {pendingApprovals.slice(0, 3).map((s) => (
              <button key={s.id} type="button" className="flex w-full gap-3 px-4 py-3 text-left hover:bg-muted/50" onClick={() => navigate("/approvals")}>
                <FileStack className="mt-0.5 size-4 shrink-0 text-info" />
                <div className="space-y-1">
                  <p className="text-sm font-medium">{s.id} awaiting review</p>
                  <p className="text-xs text-muted-foreground">
                    {facilities.find((f) => f.id === s.facilityId)?.name} · {s.month} · submitted by {s.submittedBy}
                  </p>
                </div>
              </button>
            ))}
            {aiAlerts.length + pendingApprovals.length === 0 ? <p className="px-4 py-6 text-center text-xs text-muted-foreground">Nothing needs your attention.</p> : null}
          </div>
          <div className="border-t border-border p-2">
            <Button variant="ghost" size="sm" className="w-full" onClick={() => navigate(role === "Sustainability Manager" ? "/approvals" : "/activity")}>
              {role === "Sustainability Manager" ? "Open review queue" : "Open Activity Data"}
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      <Button variant="ghost" size="icon" className="shrink-0" aria-label="Toggle theme" onClick={() => setDark((d) => !d)}>
        {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="shrink-0 gap-2 px-2">
            <CircleUser className="size-5" />
            <span className="hidden text-left text-xs leading-tight md:block">
              <span className="block font-medium">{user?.name}</span>
              <span className="block text-muted-foreground">{role}</span>
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>{user?.email}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {canSimulateRole ? (
            <>
              <DropdownMenuLabel className="text-xs text-muted-foreground">Simulate role (UI preview)</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={role}
                onValueChange={(newRole) => {
                  setRole(newRole as AppRole);
                  navigate("/");
                }}
              >
                {roleOptions.map((r) => (
                  <DropdownMenuRadioItem key={r} value={r}>
                    {r}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </>
          ) : (
            <DropdownMenuLabel className="text-xs text-muted-foreground">Signed in as {user?.appRole}</DropdownMenuLabel>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => {
              void logout();
            }}
          >
            <LogOut className="size-4" /> Sign out
          </DropdownMenuItem>
          {/* <DropdownMenuItem onClick={() => navigate("/admin")}>
            <Check className="size-4" /> Administration settings
          </DropdownMenuItem> */}
        </DropdownMenuContent>
      </DropdownMenu>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Search modules, facilities and assets…" />
        <CommandList>
          <CommandEmpty>No matching records.</CommandEmpty>
          <CommandGroup heading="Modules">
            {navTargets.map((t) => (
              <CommandItem
                key={t.to}
                value={t.label}
                onSelect={() => {
                  setOpen(false);
                  navigate(t.to);
                }}
              >
                {t.label}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Facilities">
            {facilities.map((f) => (
              <CommandItem
                key={f.id}
                value={f.name}
                onSelect={() => {
                  setOpen(false);
                  navigate("/assets");
                }}
              >
                {f.name} · {f.region}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </header>
  );
}
