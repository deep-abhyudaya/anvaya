"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  ChevronRight,
  Clock,
  Folder,
  FolderPlus,
  GitBranch,
  PanelLeft,
  Radar,
  Settings,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, useReducedMotion } from "framer-motion";
import { useAnvaya } from "@/lib/store";
import { useProjects } from "@/lib/api";
import {
  GroupByKey,
  GroupedIncidents,
  groupIncidents,
  openIncident,
  useIncidentList,
} from "@/lib/incidents";
import { CreateProjectDialog } from "@/components/create-project-dialog";
import { GroupByMenu } from "@/components/group-by";

const EXPANDED_WIDTH = 260;
const COLLAPSED_WIDTH = 64;
const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_SNAP_THRESHOLD = 120;

type SidebarState = {
  collapsed: boolean;
  setCollapsed: (value: boolean) => void;
  width: number;
  setWidth: (value: number) => void;
};

const SidebarCtx = createContext<SidebarState>({
  collapsed: false,
  setCollapsed: () => {},
  width: EXPANDED_WIDTH,
  setWidth: () => {},
});

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [width, setWidthState] = useState(EXPANDED_WIDTH);
  const [lastExpanded, setLastExpanded] = useState(EXPANDED_WIDTH);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("anvaya.sidebar.width");
    if (saved) {
      const parsed = parseInt(saved, 10);
      if (!isNaN(parsed)) {
        setWidthState(parsed);
        if (parsed > COLLAPSED_WIDTH) setLastExpanded(parsed);
      }
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("anvaya.sidebar.width", String(width));
  }, [width]);

  const collapsed = width <= SIDEBAR_SNAP_THRESHOLD;

  const setCollapsed = (value: boolean) => {
    if (value) {
      if (width > COLLAPSED_WIDTH) setLastExpanded(width);
      setWidthState(COLLAPSED_WIDTH);
    } else {
      setWidthState(lastExpanded > COLLAPSED_WIDTH ? lastExpanded : EXPANDED_WIDTH);
    }
  };

  const setWidth = (value: number) => {
    if (value < SIDEBAR_SNAP_THRESHOLD) {
      if (width > COLLAPSED_WIDTH) setLastExpanded(Math.max(EXPANDED_WIDTH, value));
      setWidthState(COLLAPSED_WIDTH);
    } else {
      const clamped = Math.min(SIDEBAR_MAX_WIDTH, Math.max(EXPANDED_WIDTH, value));
      setWidthState(clamped);
      setLastExpanded(clamped);
    }
  };

  return (
    <SidebarCtx.Provider value={{ collapsed, setCollapsed, width, setWidth }}>
      {children}
    </SidebarCtx.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarCtx);
}


type NavLink = {
  href: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
};

const mainNav: NavLink[] = [
  { href: "/sentinel", icon: Radar, label: "Sentinel" },
  { href: "/pathfinder", icon: GitBranch, label: "Pathfinder" },
  { href: "/responder", icon: Zap, label: "Responder" },
  { href: "/auditor", icon: BookOpen, label: "Auditor" },
  { href: "/settings", icon: Settings, label: "Settings" },
];


function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}


function Tooltip({
  label,
  children,
  side = "right",
}: {
  label: string;
  children: React.ReactNode;
  side?: "right" | "top" | "bottom";
}) {
  return (
    <div className="group/tooltip relative flex items-center">
      {children}
      <div
        className={cn(
          "pointer-events-none absolute z-[70] whitespace-nowrap rounded border border-hairline bg-canvas-panel px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-primary opacity-0 shadow-lg transition-opacity duration-150 group-hover/tooltip:opacity-100",
          side === "right" && "left-full top-1/2 ml-2 -translate-y-1/2",
          side === "top" && "bottom-full left-1/2 mb-2 -translate-x-1/2",
          side === "bottom" && "top-full left-1/2 mt-2 -translate-x-1/2"
        )}
      >
        {label}
      </div>
    </div>
  );
}


function NavItem({
  item,
  collapsed,
  active,
}: {
  item: NavLink;
  collapsed: boolean;
  active: boolean;
}) {
  const Icon = item.icon;
  const [hovered, setHovered] = useState(false);
  const reducedMotion = useReducedMotion();

  const state = hovered ? "hover" : active ? "selected" : "idle";

  const scaleX = state === "hover" ? 1 : state === "selected" ? 0.72 : 0.5;
  const xNudge = (scaleX - 0.5) * 12;
  const tickColor =
    state === "idle"
      ? "bg-text-secondary/[0.35]"
      : state === "selected"
        ? "bg-accent/60"
        : "bg-accent";
  const tickHeight = state === "hover" ? "h-[2px]" : "h-[1.5px]";

  const textColor =
    state === "idle"
      ? "text-text-secondary"
      : state === "selected"
        ? "text-accent/80"
        : "text-accent";

  const tickTransition = {
    duration: reducedMotion ? 0.001 : 0.2,
    ease: "easeOut" as const,
  };

  const body = collapsed ? (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex h-9 w-9 items-center justify-center rounded-md p-2 transition-colors",
        active
          ? "bg-accent/[0.12] text-accent"
          : "text-text-secondary hover:bg-surface hover:text-text-primary"
      )}
    >
      <Icon
        className={cn(
          "h-4 w-4 shrink-0",
          active && "drop-shadow-[0_0_6px_var(--color-accent-glow)]"
        )}
        strokeWidth={1.5}
      />
    </Link>
  ) : (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      className="relative flex w-full items-center gap-2 rounded-md px-3 py-2"
    >
      <div className="flex w-[30%] items-center" aria-hidden="true">
        <motion.div
          className={cn(
            "block w-full origin-left rounded-full transition-[height,background-color] duration-200 ease-out",
            tickColor,
            tickHeight
          )}
          initial={false}
          animate={{ scaleX }}
          transition={tickTransition}
        />
      </div>
      <motion.div
        className="flex items-center gap-2"
        initial={false}
        animate={{ x: xNudge }}
        transition={tickTransition}
      >
        <Icon
          className={cn(
            "h-4 w-4 shrink-0 transition-colors duration-200 ease-out",
            textColor
          )}
          strokeWidth={1.5}
        />
        <span
          className={cn(
            "text-[11px] font-medium tracking-wide transition-colors duration-200 ease-out",
            textColor
          )}
        >
          {item.label}
        </span>
      </motion.div>
    </Link>
  );

  if (collapsed) return <Tooltip label={item.label}>{body}</Tooltip>;
  return body;
}


function SectionHeader({
  icon: Icon,
  label,
  open,
  onClick,
  collapsed,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  open: boolean;
  onClick: () => void;
  collapsed: boolean;
}) {
  if (collapsed) {
    const button = (
      <button
        onClick={onClick}
        aria-expanded={open}
        className="flex h-9 w-9 items-center justify-center rounded-md text-secondary transition-colors hover:bg-canvas-subtle hover:text-primary"
      >
        <Icon className="h-4 w-4" strokeWidth={1.5} />
      </button>
    );
    return <Tooltip label={label}>{button}</Tooltip>;
  }

  return (
    <button
      onClick={onClick}
      aria-expanded={open}
      className="flex w-full items-center justify-between rounded-md px-3 py-2 text-muted transition-colors hover:bg-canvas-subtle hover:text-secondary"
    >
      <span className="flex items-center gap-3">
        <Icon className="h-4 w-4" strokeWidth={1.5} />
        <span className="text-[10px] font-medium uppercase tracking-wider">
          {label}
        </span>
      </span>
      <ChevronRight
        className={cn("h-3 w-3 transition-transform", open && "rotate-90")}
        strokeWidth={1.5}
      />
    </button>
  );
}

function GroupedList({
  groups,
  router,
  icon: Icon,
}: {
  groups: GroupedIncidents[];
  router: ReturnType<typeof useRouter>;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}) {
  return (
    <>
      {groups.map((group) => (
        <div key={group.key} className="space-y-0.5">
          {group.label && (
            <div className="px-3 py-1 text-[9px] font-medium uppercase tracking-wider text-muted">
              {group.label}
            </div>
          )}
          {group.items.map((inc) => (
            <button
              key={inc.id}
              onClick={() => openIncident(router, inc)}
              className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[11px] text-secondary transition-colors hover:bg-canvas-subtle hover:text-primary"
            >
              <Icon
                className="h-3.5 w-3.5 text-muted"
                strokeWidth={1.5}
              />
              <span className="truncate">{inc.id}</span>
            </button>
          ))}
        </div>
      ))}
    </>
  );
}


function NewProjectButton({ collapsed }: { collapsed: boolean }) {
  const { state } = useAnvaya();
  const [open, setOpen] = useState(false);

  const disabled = !state.connected;
  const tooltip = state.connected ? "New project" : "Backend offline";

  return (
    <>
      <Tooltip label={tooltip} side={collapsed ? "right" : "top"}>
        <button
          onClick={() => setOpen(true)}
          disabled={disabled}
          aria-label={tooltip}
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-canvas-subtle hover:text-primary disabled:opacity-40"
        >
          <FolderPlus className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </Tooltip>
      <CreateProjectDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}


type ProjectGroupBy = "date" | "name" | "none";

function groupProjects(
  items: { project_id: string; name: string; created_at: string }[],
  by: ProjectGroupBy
) {
  if (by === "none") {
    return [{ key: "all", label: "", items: [...items].sort((a, b) => a.name.localeCompare(b.name)) }];
  }
  if (by === "name") {
    const map = new Map<string, typeof items>();
    for (const item of items) {
      const letter = item.name.charAt(0).toUpperCase();
      const list = map.get(letter) || [];
      list.push(item);
      map.set(letter, list);
    }
    return [...map.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([key, list]) => ({ key, label: key, items: list.sort((a, b) => a.name.localeCompare(b.name)) }));
  }
  const map = new Map<string, typeof items>();
  for (const item of items) {
    const d = new Date(item.created_at).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
    const list = map.get(d) || [];
    list.push(item);
    map.set(d, list);
  }
  return [...map.entries()]
    .map(([key, list]) => ({ key, label: key, items: list.sort((a, b) => a.name.localeCompare(b.name)) }))
    .sort((a, b) => new Date(b.items[0]?.created_at || 0).getTime() - new Date(a.items[0]?.created_at || 0).getTime());
}

function ProjectsSection({ collapsed }: { collapsed: boolean }) {
  const { state, dispatch } = useAnvaya();
  const { setCollapsed } = useSidebar();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [groupBy, setGroupBy] = useState<ProjectGroupBy>("none");
  const { data, isLoading } = useProjects();
  const projects = useMemo(
    () =>
      (data?.items || []) as {
        project_id: string;
        name: string;
        created_at: string;
      }[],
    [data]
  );

  const activeProjectId = useMemo(() => {
    const match = pathname.match(/^\/projects\/([^/]+)/);
    return match ? match[1] : null;
  }, [pathname]);

  const groups = useMemo(() => groupProjects(projects, groupBy), [projects, groupBy]);

  const onHeaderClick = () => {
    if (collapsed) {
      setCollapsed(false);
      setOpen(true);
    } else {
      setOpen((o) => !o);
    }
  };

  const projectGroupOptions: { value: ProjectGroupBy; label: string }[] = [
    { value: "date", label: "Date" },
    { value: "name", label: "Name" },
    { value: "none", label: "None" },
  ];

  return (
    <div className={cn("w-full", collapsed && "w-auto")}>
      <SectionHeader
        icon={Folder}
        label="Projects"
        open={open}
        onClick={onHeaderClick}
        collapsed={collapsed}
      />
      {!collapsed && open && (
        <div className="mt-1 space-y-1.5 pl-2">
          <button
            onClick={() => setDialogOpen(true)}
            disabled={!state.connected}
            className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[11px] text-secondary transition-colors hover:bg-canvas-subtle hover:text-primary disabled:opacity-40"
          >
            <FolderPlus className="h-3.5 w-3.5 text-muted" strokeWidth={1.5} />
            New Project
          </button>

          {projects.length > 0 && (
            <GroupByMenu
              value={groupBy}
              onChange={(v) => setGroupBy(v as ProjectGroupBy)}
              options={projectGroupOptions}
            />
          )}

          {isLoading ? (
            <p className="px-3 py-1 font-mono text-[10px] text-muted">Loading...</p>
          ) : projects.length === 0 ? (
            <p className="px-3 py-1 font-mono text-[10px] text-muted">No projects yet.</p>
          ) : (
            <div className="max-h-56 space-y-1.5 overflow-y-auto">
              {groups.map((g) => (
                <div key={g.key}>
                  {g.label && (
                    <div className="px-3 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted">
                      {g.label}
                    </div>
                  )}
                  <div className="space-y-0.5">
                    {g.items.map((p) => {
                      const active = p.project_id === activeProjectId;
                      return (
                        <Link
                          key={p.project_id}
                          href={`/projects/${p.project_id}`}
                          onClick={() =>
                            dispatch({
                              type: "set-active-project",
                              value: p.project_id,
                            })
                          }
                          className={cn(
                            "relative flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[11px] transition-colors",
                            active
                              ? "bg-accent/[0.12] text-accent"
                              : "text-secondary hover:bg-canvas-subtle hover:text-primary"
                          )}
                        >
                          {active && (
                            <span className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 bg-accent" />
                          )}
                          <Folder
                            className={cn(
                              "h-3.5 w-3.5",
                              active ? "text-accent" : "text-muted"
                            )}
                            strokeWidth={1.5}
                          />
                          <span className="truncate">{p.name}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <CreateProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  );
}


function SessionsSection({ collapsed }: { collapsed: boolean }) {
  const { setCollapsed } = useSidebar();
  const [open, setOpen] = useState(false);
  const [groupBy, setGroupBy] = useState<GroupByKey>("none");
  const router = useRouter();
  const all = useIncidentList();
  const groups = useMemo(() => groupIncidents(all, groupBy), [all, groupBy]);

  const onHeaderClick = () => {
    if (collapsed) {
      setCollapsed(false);
      setOpen(true);
    } else {
      setOpen((o) => !o);
    }
  };

  return (
    <div className={cn("w-full", collapsed && "w-auto")}>
      <SectionHeader
        icon={Clock}
        label="Sessions"
        open={open}
        onClick={onHeaderClick}
        collapsed={collapsed}
      />
      {!collapsed && open && (
        <div className="mt-1 space-y-1.5 pl-2">
          <GroupByMenu value={groupBy} onChange={setGroupBy} />
          <GroupedList groups={groups} router={router} icon={Clock} />
        </div>
      )}
    </div>
  );
}



export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, setCollapsed, width, setWidth } = useSidebar();

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();

    const onMove = (ev: MouseEvent) => {
      setWidth(ev.clientX);
    };

    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  return (
    <aside
      style={{ width }}
      className="fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-hairline"
    >
      <div
        onMouseDown={startResize}
        className="absolute right-0 top-0 z-50 h-full w-2 translate-x-1/2 cursor-col-resize transition-colors hover:bg-accent/20"
        aria-label="Resize sidebar"
      />
      {}
      <div
        className={cn(
          "flex h-14 items-center gap-1 px-3",
          collapsed && "justify-center px-2"
        )}
      >
        <Tooltip
          label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          side={collapsed ? "right" : "top"}
        >
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-canvas-subtle hover:text-primary"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <PanelLeft
              className={cn("h-4 w-4", collapsed && "rotate-180")}
              strokeWidth={1.5}
            />
          </button>
        </Tooltip>
        <NewProjectButton collapsed={collapsed} />
      </div>

      {}
      <nav
        className={cn(
          "nav-scroll-fade flex-1 overflow-y-auto pt-6",
          collapsed ? "px-2" : "px-3"
        )}
        aria-label="primary"
      >
        <div className="space-y-1">
          {mainNav.map((item) => (
            <NavItem
              key={item.href}
              item={item}
              collapsed={collapsed}
              active={isActive(pathname, item.href)}
            />
          ))}
        </div>

        <div className={cn("mt-4", collapsed && "flex justify-center")}>
          <ProjectsSection collapsed={collapsed} />
        </div>

        <div className={cn("mt-1", collapsed && "flex justify-center")}>
          <SessionsSection collapsed={collapsed} />
        </div>
      </nav>
    </aside>
  );
}
