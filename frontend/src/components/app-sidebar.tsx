import { Link, useLocation } from "react-router-dom";
import {
  BadgeCheck,
  Bot,
  Boxes,
  ClipboardList,
  FileStack,
  Gauge,
  LayoutDashboard,
  Leaf,
  Settings2,
  UserCog,
  Zap,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useStore } from "@/lib/store";
import { useAuth } from "@/context/AuthContext";

// const groups = [
//   {
//     label: "Operations",
//     items: [
//       { title: "Dashboard", url: "/", icon: LayoutDashboard },
//       { title: "Facilities & Assets", url: "/assets", icon: Boxes },
//       { title: "Activity Data", url: "/activity", icon: ClipboardList },
//       { title: "Energy Management", url: "/energy", icon: Zap },
//     ],
//   },
//   {
//     label: "Sustainability",
//     items: [
//       { title: "Carbon Accounting", url: "/carbon", icon: Gauge },
//       { title: "Initiatives", url: "/initiatives", icon: Leaf },
//     ],
//   },
//   {
//     label: "Governance",
//     items: [
//       { title: "Validation & Approvals", url: "/approvals", icon: BadgeCheck },
//       // { title: "Document Repository", url: "/documents", icon: FileStack },
//       // { title: "AI Assistant", url: "/assistant", icon: Bot },
//       // { title: "Administration", url: "/admin", icon: Settings2 },
//     ],
//   },
// ];

const groups = [
  {
    label: "Operations",
    items: [
      {
        title: "Dashboard",
        url: "/",
        icon: LayoutDashboard,
      },
      {
        title: "Facilities & Assets",
        url: "/assets",
        icon: Boxes,
      },
      {
        title: "Activity Data",
        url: "/activity",
        icon: ClipboardList,
      },
      {
        title: "Energy Management",
        url: "/energy",
        icon: Zap,
      },
    ],
  },

  {
    label: "Sustainability",
    items: [
      {
        title: "Carbon Accounting",
        url: "/carbon",
        icon: Gauge,
      },

      {
        title: "Initiatives",
        url: "/initiatives",
        icon: Leaf,
      },
    ],
  },

  {
    label: "Governance",
    items: [
      {
        title: "Validation & Approvals",
        url: "/approvals",
        icon: BadgeCheck,
      },
      { title: "Document repository", url: "/documents", icon: FileStack },
      { title: "AI Assistant", url: "/assistant", icon: Bot },
      { title: "Users & Access", url: "/users", icon: UserCog },
    ],
  },
];


export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const { pathname } = useLocation();
  const { role, submissions, currentPeriod } = useStore();
  const { canOpen } = useAuth();
  const pending = submissions.filter((s) => s.status === "Submitted" || s.status === "Under Review").length;

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex items-center gap-2.5 px-1 py-1.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
            <Leaf className="size-5" />
          </span>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-sidebar-foreground">CarbonOps AI</p>
              <p className="truncate text-[11px] text-sidebar-foreground/60">Decarbonization Operations</p>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        {/* {groups.map((g) => ( */}

          {groups
  .filter((g) =>
    g.items.some((item) => canOpen(item.url))
  )
  .map((g) => (

          <SidebarGroup key={g.label}>
            {!collapsed && <SidebarGroupLabel>{g.label}</SidebarGroupLabel>}
            <SidebarGroupContent>
              <SidebarMenu>
                {/* {g.items.map((item) => { */}


                {g.items
  .filter((item) => canOpen(item.url))
  .map((item) => {


                  const active = item.url === "/" ? pathname === "/" : pathname.startsWith(item.url);
                  return (
                    <SidebarMenuItem key={item.url}>
                      <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
                        <Link to={item.url} className="flex items-center gap-2">
                          <item.icon className="size-4 shrink-0" />
                          {!collapsed && <span className="truncate">{item.title}</span>}
                          {!collapsed && item.url === "/approvals" && pending > 0 ? (
                            <span className="ml-auto rounded-full bg-sidebar-primary px-1.5 py-0.5 text-[10px] font-semibold text-sidebar-primary-foreground tabular">
                              {pending}
                            </span>
                          ) : null}
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      {!collapsed && (
        <SidebarFooter className="border-t border-sidebar-border">
          <div className="rounded-lg bg-sidebar-accent px-3 py-2.5">
            <p className="text-[11px] uppercase tracking-wide text-sidebar-foreground/60">Active role</p>
            <p className="text-sm font-medium text-sidebar-accent-foreground">{role}</p>
            <p className="mt-1 text-[11px] text-sidebar-foreground/60">{currentPeriod ? `Reporting period ${currentPeriod} · Open` : "No open reporting period"}</p>
          </div>
        </SidebarFooter>
      )}
    </Sidebar>
  );
}
