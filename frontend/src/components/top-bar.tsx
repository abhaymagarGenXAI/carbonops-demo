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
import { useRoles } from "@/hooks/useApi";

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

export function TopBar() {
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const navigate = useNavigate();
  const { role, setRole, submissions, aiAlerts, facilities, assets, initiatives, documents } = useStore();
  const { user, canSimulateRole, roleId, canOpen, logout } = useAuth();
  const { data: roleOptions = [] } = useRoles(canSimulateRole); // every role, incl. custom ones, can be previewed
  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };
  const reviewer = canOpen("/approvals"); // roles that work the review queue

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
        <span className="truncate">Jump to a page or record…</span>
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
              <button key={a.id} type="button" className="flex w-full gap-3 px-4 py-3 text-left hover:bg-muted/50" onClick={() => navigate(alertLink(a, reviewer))}>
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
            <Button variant="ghost" size="sm" className="w-full" onClick={() => navigate(reviewer ? "/approvals" : "/activity")}>
              {reviewer ? "Open review queue" : "Open Activity Data"}
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
                value={roleId ?? ""}
                onValueChange={(newRoleId) => {
                  setRole(newRoleId);
                  navigate("/");
                }}
              >
                {roleOptions.map((r) => (
                  <DropdownMenuRadioItem key={r.id} value={r.id}>
                    {r.name}
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
        <CommandInput placeholder="Jump to a page, facility, asset, submission, initiative or document…" />
        <CommandList>
          <CommandEmpty>Nothing matches.</CommandEmpty>
          <CommandGroup heading="Pages">
            {navTargets.filter((t) => canOpen(t.to)).map((t) => (
              <CommandItem key={t.to} value={t.label} onSelect={() => go(t.to)}>{t.label}</CommandItem>
            ))}
          </CommandGroup>
          {canOpen("/assets") ? (
            <CommandGroup heading="Facilities & assets">
              {facilities.map((f) => (
                <CommandItem key={f.id} value={`${f.name} ${f.code} ${f.region}`} onSelect={() => go("/assets")}>{f.name} · {f.region}</CommandItem>
              ))}
              {assets.slice(0, 200).map((a) => (
                <CommandItem key={a.id} value={`${a.name} ${a.id} ${a.type}`} onSelect={() => go("/assets")}>{a.name} · {a.id}</CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {canOpen("/activity") ? (
            <CommandGroup heading="Submissions">
              {submissions.slice(0, 200).map((s) => (
                <CommandItem key={s.id} value={`${s.id} ${s.month} ${s.status} ${facilities.find((f) => f.id === s.facilityId)?.name ?? ""}`} onSelect={() => go(reviewer && (s.status === "Submitted" || s.status === "Under Review") ? "/approvals" : "/activity")}>
                  {s.id} · {s.month} · {s.status}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {canOpen("/initiatives") ? (
            <CommandGroup heading="Initiatives">
              {initiatives.map((i) => (
                <CommandItem key={i.id} value={`${i.name} ${i.id} ${i.owner}`} onSelect={() => go("/initiatives")}>{i.name} · {i.status}</CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {canOpen("/documents") ? (
            <CommandGroup heading="Documents">
              {documents.slice(0, 200).map((d) => (
                <CommandItem key={d.id} value={`${d.name} ${d.id}`} onSelect={() => go("/documents")}>{d.name}</CommandItem>
              ))}
            </CommandGroup>
          ) : null}
        </CommandList>
      </CommandDialog>
    </header>
  );
}
