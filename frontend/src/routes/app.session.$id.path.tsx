import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpen,
  BrainCircuit,
  Check,
  ChevronDown,
  Circle,
  Clock3,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  PlayCircle,
  RotateCcw,
  Sparkles,
  Award,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";

import {
  apiErrorMessage,
  getCourse,
  setCourseActivity,
  unlockCourseModule,
  type CourseActivity,
  type CourseModule,
  type CourseProgress,
} from "@/lib/api";
import { preloadCoursePage } from "@/lib/route-prefetch";

export const Route = createFileRoute("/app/session/$id/path")({
  beforeLoad: ({ context, params }) =>
    preloadCoursePage(context.queryClient, params.id),
  head: () => ({ meta: [{ title: "Course - Lexinit" }] }),
  component: CoursePage,
});

const ACTIVITY_ICONS = {
  material: BookOpen,
  video: PlayCircle,
  flashcards: Layers3,
  assessment: BrainCircuit,
};

const ACTIVITY_ROUTES = {
  materials: "/app/session/$id/materials",
  videos: "/app/session/$id/videos",
  flashcards: "/app/session/$id/flashcards",
  assessments: "/app/session/$id/assessments",
} as const;

function CoursePage() {
  const { id } = Route.useParams();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["course", id],
    queryFn: () => getCourse(id),
    staleTime: 5_000,
  });
  const course = query.data;
  const [openModule, setOpenModule] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (!openModule && course?.current_module_id) {
      setOpenModule(course.current_module_id);
    }
  }, [course?.current_module_id, openModule]);

  const nextActivity = useMemo(
    () =>
      course?.modules
        .filter((module) => module.status === "active")
        .flatMap((module) => module.activities)
        .find((activity) => activity.status !== "completed"),
    [course],
  );

  const applyCourse = (next: CourseProgress) => {
    queryClient.setQueryData(["course", id], next);
    void queryClient.invalidateQueries({ queryKey: ["courses"] });
  };

  const toggleActivity = async (activity: CourseActivity) => {
    setBusy(activity.activity_id);
    setActionError("");
    try {
      applyCourse(
        await setCourseActivity(
          id,
          activity.activity_id,
          activity.status === "completed" ? "todo" : "completed",
        ),
      );
    } catch (error) {
      setActionError(apiErrorMessage(error, "Could not update this activity."));
    } finally {
      setBusy("");
    }
  };

  const unlock = async (module: CourseModule) => {
    setBusy(module.module_id);
    setActionError("");
    try {
      applyCourse(await unlockCourseModule(id, module.module_id));
      setOpenModule(module.module_id);
    } catch (error) {
      setActionError(apiErrorMessage(error, "Could not open this module."));
    } finally {
      setBusy("");
    }
  };

  if (query.isLoading) {
    return (
      <div className="grid min-h-[55vh] place-items-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
          className="grid h-14 w-14 place-items-center rounded-2xl bg-accent/10 text-accent"
        >
          <Sparkles className="h-6 w-6" />
        </motion.div>
      </div>
    );
  }

  if (query.isError || !course) {
    return (
      <div className="space-y-6">
        <Link
          to="/app"
          className="inline-flex h-9 w-fit items-center gap-2 rounded-full border border-border bg-card px-4 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <ArrowRight className="h-4 w-4 rotate-180" /> All courses
        </Link>
        <div className="rounded-[28px] border border-destructive/25 bg-destructive/5 p-7">
          <h1 className="font-display text-3xl tracking-tight">
            Course could not be loaded
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {apiErrorMessage(query.error, "Please try again.")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      <Link
        to="/app"
        className="inline-flex h-9 w-fit items-center gap-2 rounded-full border border-border bg-card px-4 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground"
      >
        <ArrowRight className="h-4 w-4 rotate-180" /> All courses
      </Link>

      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-[30px] border border-border bg-card p-6 shadow-[var(--shadow-elegant)] sm:p-8"
      >
        <motion.div
          animate={{ x: [0, 24, 0], y: [0, -18, 0], scale: [1, 1.08, 1] }}
          transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-accent/20 blur-3xl"
        />
        <div className="relative grid gap-8 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <h1 className="flex max-w-3xl items-center gap-3 font-display text-4xl leading-[1.02] tracking-tight sm:text-5xl">
              <Sparkles className="h-8 w-8 shrink-0 text-accent sm:h-9 sm:w-9" />
              {course.topic}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
              Learn each module through Study Materials, Video Lectures,
              Flashcards, and Assessments.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
              <span className="rounded-full border border-border bg-background/70 px-3 py-1.5">
                {course.difficulty}
              </span>
              <span>
                {course.completed_modules} of {course.total_modules} modules
                complete
              </span>
            </div>
          </div>
          <ProgressOrb percentage={course.progress_percent} />
        </div>

        {nextActivity && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.18 }}
            className="relative mt-7 flex flex-col gap-4 rounded-2xl border border-accent/30 bg-accent/10 p-5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
                Continue learning
              </div>
              <div className="mt-1 font-display text-2xl tracking-tight">
                {nextActivity.title}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {course.current_module_title}
              </p>
            </div>
            <Link
              to={ACTIVITY_ROUTES[nextActivity.route]}
              params={{ id }}
              search={{ module: nextActivity.module_id }}
              className="group inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
            >
              Continue{" "}
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
            </Link>
          </motion.div>
        )}

        {course.status === "completed" && (
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.2, duration: 0.5, ease: "easeOut" }}
            className="relative mt-7 overflow-hidden rounded-[28px] border border-amber-400/50 bg-gradient-to-br from-amber-400/20 via-background to-amber-500/10 p-6 shadow-[var(--shadow-elegant)] sm:p-8"
          >
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-amber-200/20 via-transparent to-transparent" />
            <div className="relative flex flex-col items-center text-center">
              <motion.div
                animate={{ 
                  rotate: [0, -5, 5, -5, 5, 0],
                  scale: [1, 1.1, 1.1, 1.1, 1.1, 1] 
                }}
                transition={{ duration: 1.5, repeat: Infinity, repeatDelay: 3 }}
                className="grid h-20 w-20 place-items-center rounded-full bg-gradient-to-b from-amber-300 to-amber-500 text-amber-950 shadow-lg shadow-amber-500/25"
              >
                <Award className="h-10 w-10" />
              </motion.div>
              <h2 className="mt-5 font-display text-3xl tracking-tight text-foreground sm:text-4xl">
                Course Completed!
              </h2>
              <p className="mt-2 max-w-xl text-muted-foreground">
                Outstanding work! You've mastered all {course.total_modules} modules and earned your completion badge. Check your profile to view your trophy cabinet.
              </p>
              <Link
                to="/app/profile"
                search={{ tab: "badges" }}
                className="mt-6 inline-flex h-11 items-center gap-2 rounded-full bg-amber-500 px-6 text-sm font-semibold text-amber-950 shadow-sm transition hover:bg-amber-400"
              >
                <Award className="h-4 w-4" /> View My Badges
              </Link>
            </div>
          </motion.div>
        )}
      </motion.section>

      {actionError && (
        <motion.p
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          role="alert"
          className="rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {actionError}
        </motion.p>
      )}

      <section>
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 font-display text-3xl tracking-tight">
              <Sparkles className="h-6 w-6 shrink-0 text-accent" />
              Your path through the topic
            </h2>
          </div>
          <span className="hidden text-sm text-muted-foreground sm:block">
            Completion and mastery are tracked separately
          </span>
        </div>

        <div className="mt-5 space-y-3">
          {course.modules.map((module, index) => (
            <ModuleCard
              key={module.module_id}
              index={index}
              module={module}
              sessionId={id}
              open={openModule === module.module_id}
              busy={busy}
              onToggle={() =>
                setOpenModule(
                  openModule === module.module_id ? null : module.module_id,
                )
              }
              onActivityToggle={toggleActivity}
              onUnlock={() => void unlock(module)}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function ProgressOrb({ percentage }: { percentage: number }) {
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg
        className="h-full w-full -rotate-90"
        viewBox="0 0 120 120"
        aria-hidden="true"
      >
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          className="text-muted"
        />
        <motion.circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          strokeLinecap="round"
          className="text-accent"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - percentage / 100) }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="font-display text-3xl tracking-tight">
            {percentage}%
          </div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            complete
          </div>
        </div>
      </div>
    </div>
  );
}

function ModuleCard({
  index,
  module,
  sessionId,
  open,
  busy,
  onToggle,
  onActivityToggle,
  onUnlock,
}: {
  index: number;
  module: CourseModule;
  sessionId: string;
  open: boolean;
  busy: string;
  onToggle: () => void;
  onActivityToggle: (activity: CourseActivity) => Promise<void>;
  onUnlock: () => void;
}) {
  const locked = module.status === "locked";
  const complete = module.status === "completed";
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.055, duration: 0.35 }}
      className={`overflow-hidden rounded-[24px] border bg-card shadow-sm transition ${open ? "border-accent/45 shadow-[var(--shadow-elegant)]" : "border-border"}`}
    >
      <button
        type="button"
        onClick={locked ? undefined : onToggle}
        className={`flex w-full items-center gap-4 p-5 text-left sm:p-6 ${locked ? "cursor-default" : "hover:bg-muted/35"}`}
      >
        <div
          className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${complete ? "bg-emerald-500 text-white" : locked ? "bg-muted text-muted-foreground" : "bg-accent text-accent-foreground"}`}
        >
          {complete ? (
            <Check className="h-5 w-5" />
          ) : locked ? (
            <LockKeyhole className="h-4 w-4" />
          ) : (
            <span className="font-display text-lg">{index + 1}</span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-2xl tracking-tight">
              {module.title}
            </h3>
            {module.needs_review && (
              <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-700 dark:text-amber-300">
                Review recommended
              </span>
            )}
          </div>
          <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">
            {module.description}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Clock3 className="h-3.5 w-3.5" /> {module.estimated_minutes} min
            </span>
            <span>
              {module.completed_activities}/{module.total_activities} activities
            </span>
            {module.mastery_percent != null && (
              <span>Mastery {module.mastery_percent}%</span>
            )}
          </div>
        </div>
        {!locked && (
          <motion.span animate={{ rotate: open ? 180 : 0 }}>
            <ChevronDown className="h-5 w-5 text-muted-foreground" />
          </motion.span>
        )}
      </button>

      {locked && (
        <div className="flex flex-col gap-3 border-t border-border bg-muted/25 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-sm text-muted-foreground">
            Finish the previous module, or continue at your own pace.
          </p>
          <button
            type="button"
            onClick={onUnlock}
            disabled={busy === module.module_id}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-full border border-border bg-card px-4 text-sm font-semibold transition hover:border-accent/50 hover:bg-accent/5 disabled:opacity-50"
          >
            {busy === module.module_id && (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            )}{" "}
            Continue anyway
          </button>
        </div>
      )}

      <AnimatePresence initial={false}>
        {open && !locked && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="space-y-2 border-t border-border bg-background/35 p-4 sm:p-5">
              {module.activities.map((activity, activityIndex) => (
                <ActivityRow
                  key={activity.activity_id}
                  activity={activity}
                  index={activityIndex}
                  sessionId={sessionId}
                  busy={busy === activity.activity_id}
                  onToggle={() => void onActivityToggle(activity)}
                />
              ))}
              {module.activities.length === 0 && (
                <p className="rounded-2xl bg-muted p-4 text-sm text-muted-foreground">
                  No activities were generated for this module.
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}

function ActivityRow({
  activity,
  index,
  sessionId,
  busy,
  onToggle,
}: {
  activity: CourseActivity;
  index: number;
  sessionId: string;
  busy: boolean;
  onToggle: () => void;
}) {
  const Icon = ACTIVITY_ICONS[activity.type];
  const complete = activity.status === "completed";
  const manual = activity.type === "material" || activity.type === "flashcards";
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.045 }}
      className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4 sm:flex-row sm:items-center"
    >
      <div
        className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${complete ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground"}`}
      >
        {complete ? (
          <Check className="h-4 w-4" />
        ) : (
          <Icon className="h-4 w-4" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{activity.title}</div>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {activity.detail} · {activity.item_count} item
          {activity.item_count === 1 ? "" : "s"}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {manual && (
          <button
            type="button"
            onClick={onToggle}
            disabled={busy}
            className={`inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold transition disabled:opacity-50 ${complete ? "text-muted-foreground hover:bg-muted" : "bg-accent/10 text-accent hover:bg-accent/15"}`}
          >
            {busy ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : complete ? (
              <RotateCcw className="h-3.5 w-3.5" />
            ) : (
              <Circle className="h-3.5 w-3.5" />
            )}
            {complete ? "Undo" : "Mark reviewed"}
          </button>
        )}
        <Link
          to={ACTIVITY_ROUTES[activity.route]}
          params={{ id: sessionId }}
          search={{
            module: activity.module_id,
            ...(activity.type === "assessment" && activity.latest_submission_id
              ? { submission: activity.latest_submission_id }
              : {}),
          }}
          className="inline-flex h-9 items-center gap-1.5 rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground transition hover:opacity-90"
        >
          Open <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </motion.div>
  );
}
