import {
  Link,
  Outlet,
  useNavigate,
  useParams,
  useRouterState,
} from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import {
  BarChart3,
  Award,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  FileText,
  History,
  Layers3,
  LibraryBig,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  PlayCircle,
  Search,
  UserRound,
  X,
} from "lucide-react";
import {
  type ComponentType,
  type ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";

import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  getActiveGenerationRuns,
  getCourse,
  getSessions,
  logout,
  type GenerationRun,
  type LearningSession,
} from "@/lib/api";
import { sessionLevel, sessionTitle } from "@/lib/session-utils";
import { useCurrentUser } from "@/hooks/use-current-user";

const SIDEBAR_STORAGE_KEY = "lexinit.sidebar.collapsed";

export function AppShell({ children }: { children?: ReactNode }) {
  const navigate = useNavigate();
  const reduceMotion = useReducedMotion();
  const routeKey = useRouterState({
    select: (state) => state.location.href,
  });
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  });
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    const handleAuthenticationRequired = () => {
      void navigate({ to: "/login" });
    };
    window.addEventListener(
      "lexinit:authentication-required",
      handleAuthenticationRequired,
    );
    return () =>
      window.removeEventListener(
        "lexinit:authentication-required",
        handleAuthenticationRequired,
      );
  }, [navigate]);

  return (
    <div className="h-dvh overflow-hidden bg-background text-foreground">
      <TopBar />
      <div className="flex h-[calc(100dvh-64px)] min-w-0 overflow-hidden">
        <SessionsSidebar
          collapsed={collapsed}
          onSidebarToggle={() => setCollapsed((value) => !value)}
          onSearchOpen={() => setSearchOpen(true)}
        />
        <main className="app-scrollbar min-w-0 flex-1 overflow-y-auto">
          <MobileCourseNavigation />
          <motion.div
            key={routeKey}
            initial={reduceMotion ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 lg:px-10 lg:py-8"
          >
            {children ?? <Outlet />}
          </motion.div>
        </main>
      </div>
      <SessionSearchModal open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}

function MobileCourseNavigation() {
  const params = useParams({ strict: false }) as { id?: string };
  const sessionId = params.id;
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const selectedModuleId = useRouterState({
    select: (state) => {
      const search = state.location.search as { module?: unknown };
      return typeof search.module === "string" ? search.module : undefined;
    },
  });
  const [open, setOpen] = useState(false);
  const course = useQuery({
    queryKey: ["course", sessionId],
    queryFn: () => getCourse(sessionId!),
    enabled: Boolean(sessionId),
    staleTime: 5_000,
  });

  useEffect(() => setOpen(false), [pathname, selectedModuleId]);

  if (!sessionId) return null;

  const selectedModule = course.data?.modules.find(
    (module) => module.module_id === selectedModuleId,
  );
  const onLearningPath = pathname.endsWith("/path");
  const onAdditionalResources = pathname.endsWith("/resources");

  return (
    <div className="sticky top-0 z-30 border-b border-border bg-background/92 px-4 py-2.5 backdrop-blur-xl lg:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open learning path"
          className="flex min-h-12 w-full items-center gap-3 rounded-2xl border border-border bg-card px-3.5 text-left shadow-sm transition active:scale-[0.99]"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent">
            <BookOpen className="h-4.5 w-4.5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">
              Learning path
            </span>
            <span className="block truncate text-sm font-semibold text-foreground">
              {onAdditionalResources
                ? "Additional Resources"
                : selectedModule?.title ||
                  (onLearningPath ? "Course overview" : "Choose a module")}
            </span>
          </span>
          {course.data && (
            <span className="shrink-0 text-xs font-semibold text-muted-foreground">
              {course.data.progress_percent}%
            </span>
          )}
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>

        <SheetContent
          side="left"
          className="flex h-dvh w-[min(92vw,390px)] flex-col gap-0 overflow-hidden border-border bg-card p-0 sm:max-w-[390px]"
        >
          <SheetHeader className="shrink-0 border-b border-border bg-background/70 px-5 pb-5 pt-6 text-left">
            <SheetTitle className="pr-8 font-display text-2xl tracking-tight">
              Learning path
            </SheetTitle>
            <SheetDescription className="line-clamp-2 leading-5">
              {course.data?.topic || "Your learning path and module activities"}
            </SheetDescription>
            {course.data && (
              <div className="pt-2">
                <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
                  <span>
                    {course.data.completed_modules}/{course.data.total_modules}{" "}
                    modules
                  </span>
                  <span>{course.data.progress_percent}% complete</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${course.data.progress_percent}%` }}
                    transition={{ duration: 0.55, ease: "easeOut" }}
                    className="h-full rounded-full bg-accent"
                  />
                </div>
              </div>
            )}
          </SheetHeader>

          <div className="app-scrollbar min-h-0 flex-1 overflow-y-auto px-3 py-4">
            <Link
              to="/app/session/$id/path"
              params={{ id: sessionId }}
              onClick={() => setOpen(false)}
              className={`flex min-h-12 items-center gap-3 rounded-2xl px-3.5 font-semibold transition ${onLearningPath ? "bg-accent text-accent-foreground shadow-sm" : "bg-accent/10 text-accent hover:bg-accent/15"}`}
            >
              <BookOpen className="h-5 w-5" />
              <span className="flex-1">Course overview</span>
              <span className="text-xs opacity-75">Overview</span>
            </Link>

            {course.isLoading && (
              <div className="grid place-items-center py-12 text-muted-foreground">
                <LoaderCircle className="h-6 w-6 animate-spin" />
              </div>
            )}

            <div className="mt-4 space-y-3">
              {course.data?.modules.map((module, index) => {
                const selected = module.module_id === selectedModuleId;
                const locked = module.status === "locked";
                return (
                  <motion.section
                    key={module.module_id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.035 }}
                    className={`overflow-hidden rounded-2xl border ${selected ? "border-accent/45 bg-accent/5" : "border-border bg-background/45"}`}
                  >
                    <Link
                      to="/app/session/$id/path"
                      params={{ id: sessionId }}
                      onClick={() => setOpen(false)}
                      className="flex min-h-14 items-center gap-3 px-3.5 py-2.5"
                    >
                      <span
                        className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-bold ${module.status === "completed" ? "bg-emerald-500 text-white" : selected ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground"}`}
                      >
                        {module.status === "completed" ? (
                          <CheckCircle2 className="h-4.5 w-4.5" />
                        ) : locked ? (
                          <LockKeyhole className="h-4 w-4" />
                        ) : (
                          index + 1
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold">
                          {module.title}
                        </span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {locked
                            ? "Locked"
                            : `${module.completed_activities}/${module.total_activities} activities`}
                        </span>
                      </span>
                      {!locked && (
                        <span className="text-xs font-semibold text-accent">
                          {module.progress_percent}%
                        </span>
                      )}
                    </Link>

                    {!locked && (
                      <div className="grid grid-cols-2 gap-1.5 border-t border-border/70 p-2.5">
                        {module.activities.map((activity) => {
                          const item = COURSE_ACTIVITY_LINKS[activity.type];
                          const Icon = item.icon;
                          const active =
                            selected && pathname.endsWith(`/${activity.route}`);
                          return (
                            <Link
                              key={activity.activity_id}
                              to={item.to}
                              params={{ id: sessionId }}
                              search={{
                                module: module.module_id,
                                ...(activity.type === "assessment" &&
                                activity.latest_submission_id
                                  ? {
                                      submission: activity.latest_submission_id,
                                    }
                                  : {}),
                              }}
                              onClick={() => setOpen(false)}
                              className={`flex min-h-10 items-center gap-2 rounded-xl px-2.5 text-xs font-medium transition ${active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                            >
                              <Icon className="h-4 w-4 shrink-0" />
                              <span className="truncate">{item.label}</span>
                              {activity.status === "completed" && (
                                <CheckCircle2 className="ml-auto h-3.5 w-3.5 shrink-0" />
                              )}
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </motion.section>
                );
              })}
            </div>
            <Link
              to="/app/session/$id/resources"
              params={{ id: sessionId }}
              search={{ module: undefined }}
              onClick={() => setOpen(false)}
              aria-current={onAdditionalResources ? "page" : undefined}
              className={`mt-3 flex min-h-14 items-center gap-3 rounded-2xl border px-3.5 py-2.5 transition ${onAdditionalResources ? "border-accent/45 bg-accent/10 text-accent" : "border-border bg-background/45 text-foreground hover:bg-muted"}`}
            >
              <span
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${onAdditionalResources ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground"}`}
              >
                <LibraryBig className="h-4.5 w-4.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">
                  Additional Resources
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Course library
                </span>
              </span>
            </Link>
            {course.data && (
              <div className="mt-4">
                <CourseCompletionBadge course={course.data} />
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function TopBar() {
  const { data: user } = useCurrentUser();
  const { data } = useQuery({
    queryKey: ["generation-runs", "active"],
    queryFn: getActiveGenerationRuns,
    refetchInterval: 4_000,
    staleTime: 1_000,
  });
  const activeRun = data?.runs[0];
  
  const planLabel = user?.plan === "pro" ? "Pro" : user?.plan === "plus" ? "Plus" : "Free";

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/88 backdrop-blur-xl">
      <div className="flex h-16 items-center justify-between px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Link to="/app" className="flex min-w-0 items-center gap-3">
            <Logo className="h-9 w-9 shrink-0 text-foreground" />
            <span className="hidden truncate font-display text-2xl tracking-tight text-foreground sm:inline">
              Lexinit
            </span>
          </Link>
        </div>

        <nav className="flex items-center gap-1">
          {activeRun && <GenerationRunIndicator run={activeRun} />}
          <div className="hidden items-center gap-2 pr-2 sm:flex">
            <Link
              to="/app/profile"
              search={{ tab: "security" }}
              className="rounded-full bg-accent/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-accent transition hover:bg-accent/20"
            >
              {planLabel}
            </Link>
            <Link
              to="/app/pricing"
              className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground shadow-sm transition hover:opacity-90"
            >
              Upgrade
            </Link>
          </div>
          <TopIcon
            label="Progress"
            icon={BarChart3}
            to="/app/insights"
            hiddenOnMobile
          />
          <TopIcon label="Profile" icon={UserRound} to="/app/profile" />
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}

function GenerationRunIndicator({ run }: { run: GenerationRun }) {
  return (
    <Link
      to="/app"
      aria-label={`${run.message} ${run.progress}%`}
      className="mr-1 inline-flex h-10 items-center gap-2 rounded-full border border-accent/25 bg-accent/10 px-3 text-xs font-semibold text-accent transition hover:bg-accent/15"
    >
      <LoaderCircle className="h-4 w-4 animate-spin" />
      <span className="hidden max-w-32 truncate sm:inline">
        {run.topic || "Generating"}
      </span>
      <span>{run.progress}%</span>
    </Link>
  );
}

function TopIcon({
  label,
  icon: Icon,
  to,
  hiddenOnMobile = false,
}: {
  label: string;
  icon: ComponentType<{ className?: string }>;
  to: "/app/insights" | "/app/profile";
  hiddenOnMobile?: boolean;
}) {
  return (
    <Link
      to={to}
      aria-label={label}
      title={label}
      className={`${hiddenOnMobile ? "hidden sm:grid" : "grid"} h-10 w-10 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground`}
    >
      <Icon className="h-5 w-5" />
    </Link>
  );
}

function SessionsSidebar({
  collapsed,
  onSidebarToggle,
  onSearchOpen,
}: {
  collapsed: boolean;
  onSidebarToggle: () => void;
  onSearchOpen: () => void;
}) {
  const params = useParams({ strict: false }) as { id?: string };
  const activeId = params.id;
  const course = useQuery({
    queryKey: ["course", activeId],
    queryFn: () => getCourse(activeId!),
    enabled: Boolean(activeId),
    staleTime: 5_000,
  });
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sessions", "sidebar"],
    queryFn: () => getSessions(),
    enabled: !activeId,
    staleTime: 15_000,
  });
  const sessions = normalizeSessions(data?.sessions);

  if (activeId) {
    return (
      <CourseSidebar
        sessionId={activeId}
        collapsed={collapsed}
        onSidebarToggle={onSidebarToggle}
        course={course.data}
        loading={course.isLoading}
      />
    );
  }

  return (
    <aside
      className={`hidden h-full shrink-0 overflow-hidden border-r border-border bg-card/80 backdrop-blur-xl transition-[width] duration-300 ease-out lg:flex ${
        collapsed ? "w-[72px]" : "w-[280px]"
      }`}
    >
      <div className="flex min-h-0 w-full flex-col p-2.5">
        <div className="flex h-11 items-center gap-2">
          <button
            type="button"
            onClick={onSidebarToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-5 w-5" />
            ) : (
              <PanelLeftClose className="h-5 w-5" />
            )}
          </button>
          <SidebarLabel collapsed={collapsed}>
            <span className="font-display text-lg font-semibold tracking-tight text-foreground">
              My courses
            </span>
          </SidebarLabel>
        </div>

        <div className="mt-2">
          <RailLink
            collapsed={collapsed}
            icon={LayoutDashboard}
            label="Dashboard"
            to="/app"
          />
        </div>

        <div className="relative mt-1 h-11">
          <Link
            to="/app/new-course"
            aria-label="New course"
            className={`absolute inset-0 flex h-11 min-w-0 items-center gap-2.5 overflow-hidden rounded-full bg-accent/10 px-3 font-medium text-accent shadow-sm transition-[opacity,background-color] duration-200 hover:bg-accent/20 ${
              collapsed ? "pointer-events-none opacity-0" : "opacity-100"
            }`}
          >
            <Plus className="h-5 w-5 shrink-0" />
            <span className="truncate">New course</span>
          </Link>
          <Link
            to="/app/new-course"
            aria-label="New course"
            className={`absolute left-0 top-0 grid h-11 w-11 place-items-center rounded-full bg-accent/10 text-accent shadow-sm transition-[opacity,background-color] duration-200 hover:bg-accent/20 ${
              collapsed ? "opacity-100" : "pointer-events-none opacity-0"
            }`}
          >
            <Plus className="h-5 w-5" />
          </Link>
        </div>

        <div className="mt-4 grid gap-1">
          <RailLink
            collapsed={collapsed}
            icon={BarChart3}
            label="Progress"
            to="/app/insights"
          />
          <RailLink
            collapsed={collapsed}
            icon={Award}
            label="Badges"
            to="/app/profile"
            search={{ tab: "badges" }}
          />
          <RailAction
            collapsed={collapsed}
            icon={Search}
            label="Search courses"
            onClick={onSearchOpen}
          />
        </div>

        <div className="mt-6 min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {collapsed ? (
            <RailAction
              collapsed={collapsed}
              icon={History}
              label="Recent courses"
            />
          ) : (
            <ul className="mt-2 space-y-1">
              {sessions.map((session) => {
                const active = session.id === activeId;
                return (
                  <li key={session.id}>
                    <Link
                      to="/app/session/$id/path"
                      params={{ id: session.id }}
                      aria-label={session.title}
                      className={`group flex items-center gap-2.5 rounded-2xl px-3 py-3 transition ${
                        active
                          ? "bg-accent/10 text-accent"
                          : "text-foreground hover:bg-muted"
                      }`}
                    >
                      <span
                        className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-semibold ${
                          active
                            ? "bg-card text-accent"
                            : "bg-muted text-muted-foreground group-hover:bg-card"
                        }`}
                      >
                        {session.title.charAt(0)}
                      </span>
                      <SidebarLabel collapsed={collapsed}>
                        <span className="block truncate text-sm font-medium leading-5">
                          {session.title}
                        </span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {session.adaptive ? "Focused practice · " : ""}
                          {session.level}
                        </span>
                      </SidebarLabel>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {sessions.length === 0 && !isLoading && !isError && !collapsed && (
            <p className="mt-4 rounded-2xl bg-muted px-4 py-3 text-xs leading-5 text-muted-foreground">
              No courses yet. Start a new topic to build your first course.
            </p>
          )}

          {isError && !collapsed && (
            <p className="mt-4 rounded-2xl bg-muted px-4 py-3 text-xs leading-5 text-muted-foreground">
              Sign in to load your saved courses.
            </p>
          )}
        </div>
      </div>
    </aside>
  );
}

const COURSE_ACTIVITY_LINKS = {
  material: {
    label: "Study Materials",
    icon: FileText,
    to: "/app/session/$id/materials",
  },
  video: {
    label: "Video Lectures",
    icon: PlayCircle,
    to: "/app/session/$id/videos",
  },
  flashcards: {
    label: "Flashcards",
    icon: Layers3,
    to: "/app/session/$id/flashcards",
  },
  assessment: {
    label: "Assessments",
    icon: BrainCircuit,
    to: "/app/session/$id/assessments",
  },
} as const;

function CourseSidebar({
  sessionId,
  collapsed,
  onSidebarToggle,
  course,
  loading,
}: {
  sessionId: string;
  collapsed: boolean;
  onSidebarToggle: () => void;
  course?: Awaited<ReturnType<typeof getCourse>>;
  loading: boolean;
}) {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const selectedModuleId = useRouterState({
    select: (state) => {
      const search = state.location.search as { module?: unknown };
      return typeof search.module === "string" ? search.module : undefined;
    },
  });
  const [expandedModuleId, setExpandedModuleId] = useState<string | null>(null);
  const onLearningPath = pathname.endsWith("/path");
  const onAdditionalResources = pathname.endsWith("/resources");

  useEffect(() => {
    if (!course) return;
    if (
      selectedModuleId &&
      course.modules.some((module) => module.module_id === selectedModuleId)
    ) {
      setExpandedModuleId(selectedModuleId);
      return;
    }
    setExpandedModuleId((current) =>
      current && course.modules.some((module) => module.module_id === current)
        ? current
        : course.current_module_id || course.modules[0]?.module_id || null,
    );
  }, [course, selectedModuleId]);

  return (
    <aside
      className={`hidden h-full shrink-0 overflow-hidden border-r border-border bg-card transition-[width] duration-300 ease-out lg:flex ${collapsed ? "w-[72px]" : "w-[348px]"}`}
    >
      <div className="flex min-h-0 w-full flex-col">
        <div
          className={`flex min-h-16 shrink-0 items-center border-b border-border ${collapsed ? "justify-center px-2" : "gap-2 px-3"}`}
        >
          <button
            type="button"
            onClick={onSidebarToggle}
            aria-label={
              collapsed
                ? "Expand course navigation"
                : "Collapse course navigation"
            }
            className="grid h-10 w-10 shrink-0 place-items-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-5 w-5" />
            ) : (
              <PanelLeftClose className="h-5 w-5" />
            )}
          </button>
          {!collapsed && (
            <span className="font-display text-lg font-semibold tracking-tight">
              Learning path
            </span>
          )}
        </div>

        <Link
          to="/app/session/$id/path"
          params={{ id: sessionId }}
          aria-current={onLearningPath ? "page" : undefined}
          className={`flex min-h-13 shrink-0 items-center border-b border-border font-semibold text-accent transition hover:bg-accent/10 ${collapsed ? "justify-center px-2" : "gap-3 px-4"} ${onLearningPath ? "bg-accent/15" : ""}`}
          aria-label="Course overview"
        >
          <BookOpen className="h-5 w-5 shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1">Course overview</span>
              <span className="text-xs text-muted-foreground">Overview</span>
            </>
          )}
        </Link>

        <div className="app-scrollbar min-h-0 flex-1 overflow-y-auto">
          {loading && (
            <div className="grid place-items-center py-8 text-muted-foreground">
              <LoaderCircle className="h-5 w-5 animate-spin" />
            </div>
          )}
          <div>
            {course?.modules.map((module, index) => (
              <div
                key={module.module_id}
                className={`border-b border-border ${module.module_id === selectedModuleId ? "border-l-2 border-l-accent" : ""}`}
              >
                <button
                  type="button"
                  onClick={() =>
                    module.status !== "locked" &&
                    setExpandedModuleId((current) =>
                      current === module.module_id ? null : module.module_id,
                    )
                  }
                  disabled={module.status === "locked"}
                  className={`flex w-full items-center text-left transition hover:bg-muted/70 disabled:cursor-not-allowed ${collapsed ? "min-h-13 justify-center px-2" : "min-h-15 gap-3 px-4 py-3"} ${module.module_id === selectedModuleId ? "bg-accent/10" : expandedModuleId === module.module_id ? "bg-muted/55" : ""}`}
                  title={module.title}
                >
                  <span
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold ${module.status === "completed" ? "bg-accent text-accent-foreground" : "bg-muted text-foreground"}`}
                  >
                    {module.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4" />
                    ) : (
                      index + 1
                    )}
                  </span>
                  {!collapsed && (
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-2 block text-sm font-semibold leading-5">
                        {module.title}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {module.completed_activities}/{module.total_activities}{" "}
                        complete
                      </span>
                    </span>
                  )}
                  {!collapsed &&
                    (module.status === "locked" ? (
                      <LockKeyhole className="h-4 w-4 shrink-0 text-muted-foreground" />
                    ) : (
                      <ChevronDown
                        className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${expandedModuleId === module.module_id ? "rotate-180" : ""}`}
                      />
                    ))}
                </button>
                {!collapsed &&
                  module.status !== "locked" &&
                  expandedModuleId === module.module_id && (
                    <div className="border-t border-border/70 bg-background/35 py-1.5">
                      {module.activities.map((activity) => {
                        const item = COURSE_ACTIVITY_LINKS[activity.type];
                        const Icon = item.icon;
                        return (
                          <Link
                            key={activity.activity_id}
                            to={item.to}
                            params={{ id: sessionId }}
                            search={{
                              module: module.module_id,
                              ...(activity.type === "assessment" &&
                              activity.latest_submission_id
                                ? { submission: activity.latest_submission_id }
                                : {}),
                            }}
                            aria-current={
                              module.module_id === selectedModuleId &&
                              pathname.endsWith(`/${activity.route}`)
                                ? "page"
                                : undefined
                            }
                            className={`flex min-h-10 items-center gap-3 border-l-2 px-5 py-2 text-sm font-medium transition ${module.module_id === selectedModuleId && pathname.endsWith(`/${activity.route}`) ? "border-l-accent bg-accent/15 text-accent" : "border-l-transparent text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                          >
                            {activity.status === "completed" ? (
                              <CheckCircle2 className="h-4 w-4 shrink-0 text-accent" />
                            ) : (
                              <Icon className="h-4 w-4 shrink-0" />
                            )}
                            <span className="min-w-0 flex-1 truncate">
                              {item.label}
                            </span>
                            {activity.item_count > 0 && (
                              <span className="text-xs">
                                {activity.item_count}
                              </span>
                            )}
                          </Link>
                        );
                      })}
                    </div>
                  )}
              </div>
            ))}
          </div>
          <Link
            to="/app/session/$id/resources"
            params={{ id: sessionId }}
            search={{ module: undefined }}
            aria-label="Additional Resources"
            aria-current={onAdditionalResources ? "page" : undefined}
            className={`flex min-h-14 items-center border-b border-border transition hover:bg-muted ${collapsed ? "justify-center px-2" : "gap-3 px-4 py-3"} ${onAdditionalResources ? "border-l-2 border-l-accent bg-accent/10 text-accent" : "text-foreground"}`}
          >
            <span
              className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${onAdditionalResources ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground"}`}
            >
              <LibraryBig className="h-4 w-4" />
            </span>
            {!collapsed && (
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">
                  Additional Resources
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Course library
                </span>
              </span>
            )}
          </Link>
          {course && (
            <div className="p-3">
              <CourseCompletionBadge course={course} compact={collapsed} />
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function CourseCompletionBadge({
  course,
  compact = false,
}: {
  course: Awaited<ReturnType<typeof getCourse>>;
  compact?: boolean;
}) {
  const earned = course.status === "completed";

  if (compact) {
    return (
      <Link
        to="/app/profile"
        search={{ tab: "badges" }}
        aria-label={
          earned ? "View earned course badge" : "Course badge progress"
        }
        title={earned ? "View earned course badge" : "Course badge progress"}
        className={`grid h-11 w-11 place-items-center rounded-full transition ${earned ? "bg-amber-400 text-amber-950 shadow-sm" : "bg-muted text-muted-foreground hover:text-foreground"}`}
      >
        <Award className="h-5 w-5" />
      </Link>
    );
  }

  return (
    <Link
      to="/app/profile"
      search={{ tab: "badges" }}
      className={`group block rounded-2xl border p-3.5 transition hover:-translate-y-0.5 ${earned ? "border-amber-400/45 bg-gradient-to-br from-amber-400/20 via-card to-accent/10 shadow-sm" : "border-border bg-background/45 hover:border-accent/35"}`}
    >
      <div className="flex items-center gap-3">
        <span
          className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${earned ? "bg-amber-400 text-amber-950" : "bg-muted text-muted-foreground"}`}
        >
          {earned ? (
            <Award className="h-5 w-5" />
          ) : (
            <LockKeyhole className="h-4.5 w-4.5" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">
            {earned ? "Badge earned" : "Completion badge"}
          </span>
          <span className="block truncate text-sm font-semibold">
            {earned
              ? "Course completed"
              : `${course.progress_percent}% complete`}
          </span>
        </span>
        <span className="text-xs font-semibold text-accent opacity-0 transition group-hover:opacity-100">
          Profile
        </span>
      </div>
    </Link>
  );
}

function RailLink({
  collapsed,
  icon: Icon,
  label,
  to,
  search,
}: {
  collapsed: boolean;
  icon: ComponentType<{ className?: string }>;
  label: string;
  to: "/app" | "/app/insights" | "/app/profile";
  search?: Record<string, unknown>;
}) {
  return (
    <Link
      to={to}
      search={search}
      aria-label={label}
      title={label}
      activeOptions={{ exact: to === "/app" }}
      activeProps={{ className: "bg-accent/10 text-accent" }}
      className="grid h-11 w-full grid-cols-[44px_minmax(0,1fr)] items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
    >
      <span className="grid h-11 w-11 place-items-center">
        <Icon className="h-5 w-5 shrink-0" />
      </span>
      <SidebarLabel collapsed={collapsed}>{label}</SidebarLabel>
    </Link>
  );
}

function RailAction({
  collapsed,
  icon: Icon,
  label,
  onClick,
}: {
  collapsed: boolean;
  icon: ComponentType<{ className?: string }>;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="grid h-11 w-full grid-cols-[44px_minmax(0,1fr)] items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
    >
      <span className="grid h-11 w-11 place-items-center">
        <Icon className="h-5 w-5 shrink-0" />
      </span>
      <SidebarLabel collapsed={collapsed}>{label}</SidebarLabel>
    </button>
  );
}

function SidebarLabel({
  collapsed,
  children,
}: {
  collapsed: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={`min-w-0 overflow-hidden whitespace-nowrap text-left transition-opacity duration-150 ${
        collapsed ? "opacity-0" : "opacity-100"
      }`}
    >
      {children}
    </span>
  );
}

function normalizeSessions(sessions?: LearningSession[]) {
  if (!sessions || sessions.length === 0) return [];
  return sessions.map((session) => ({
    id: session._id,
    title: sessionTitle(session),
    level: sessionLevel(session),
    adaptive: session.generation_kind === "adaptive",
  }));
}

function SessionSearchModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["sessions", query],
    queryFn: () => getSessions(query),
    enabled: open,
    staleTime: 15_000,
  });
  const sessions = useMemo(
    () => normalizeSessions(data?.sessions),
    [data?.sessions],
  );

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  if (!open) return null;

  const openSession = (sessionId: string) => {
    onOpenChange(false);
    navigate({ to: "/app/session/$id/path", params: { id: sessionId } });
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-background/70 p-4 backdrop-blur-sm"
      onMouseDown={() => onOpenChange(false)}
    >
      <div
        className="mx-auto mt-20 w-full max-w-xl overflow-hidden rounded-3xl border border-border bg-card shadow-[var(--shadow-elegant)]"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <Search className="h-5 w-5 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
            placeholder="Search courses..."
            className="h-10 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close search"
            className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="app-scrollbar max-h-[420px] overflow-y-auto p-2">
          {isLoading && (
            <p className="px-4 py-6 text-sm text-muted-foreground">
              Loading courses...
            </p>
          )}
          {!isLoading && sessions.length === 0 && (
            <p className="px-4 py-6 text-sm text-muted-foreground">
              No matching courses found.
            </p>
          )}
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              onClick={() => openSession(session.id)}
              className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left transition hover:bg-muted"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-muted text-sm font-semibold text-muted-foreground">
                {session.title.charAt(0)}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">
                  {session.title}
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {session.level}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
