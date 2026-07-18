import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpenCheck,
  Clock3,
  Layers3,
  LoaderCircle,
  Sparkles,
} from "lucide-react";
import { motion } from "motion/react";

import { getCourses } from "@/lib/api";

export function CourseDashboard() {
  const query = useQuery({
    queryKey: ["courses"],
    queryFn: getCourses,
    staleTime: 15_000,
  });
  const courses = query.data?.courses ?? [];
  const current =
    courses.find((course) => course.status === "in_progress") ?? courses[0];

  if (query.isLoading) {
    return (
      <div className="grid h-44 place-items-center rounded-[26px] border border-border bg-card">
        <LoaderCircle className="h-6 w-6 animate-spin text-accent" />
      </div>
    );
  }
  if (query.isError || courses.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.06 }}
      className="space-y-5"
    >
      {current && (
        <div className="relative overflow-hidden rounded-[28px] border border-border bg-primary p-6 text-primary-foreground shadow-[var(--shadow-elegant)] sm:p-8">
          <motion.div
            animate={{ x: [0, 32, 0], y: [0, -20, 0] }}
            transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
            className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full bg-accent/35 blur-3xl"
          />
          <div className="relative grid gap-6 sm:grid-cols-[1fr_auto] sm:items-end">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.17em] text-primary-foreground/70">
                <Sparkles className="h-4 w-4" /> Continue learning
              </div>
              <h2 className="mt-3 font-display text-3xl tracking-tight sm:text-4xl">
                {current.topic}
              </h2>
              <p className="mt-2 text-sm text-primary-foreground/75">
                {current.current_module_title
                  ? `Next: ${current.current_module_title}`
                  : "Your guided course is ready."}
              </p>
              <div className="mt-5 flex max-w-xl items-center gap-3">
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-primary-foreground/15">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${current.progress_percent}%` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="h-full rounded-full bg-accent"
                  />
                </div>
                <span className="text-sm font-semibold">
                  {current.progress_percent}%
                </span>
              </div>
            </div>
            <Link
              to="/app/session/$id/path"
              params={{ id: current.session_id }}
              className="group inline-flex h-11 items-center justify-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-primary shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
            >
              Resume course{" "}
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
            </Link>
          </div>
        </div>
      )}

      <div>
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 font-display text-3xl tracking-tight">
              <BookOpenCheck className="h-6 w-6 shrink-0 text-accent" />
              Keep building momentum
            </h2>
          </div>
          <span className="hidden text-sm text-muted-foreground sm:block">
            {courses.length} saved course{courses.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {courses.slice(0, 6).map((course, index) => (
            <motion.div
              key={course.session_id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 + index * 0.045 }}
            >
              <Link
                to="/app/session/$id/path"
                params={{ id: course.session_id }}
                className="group block h-full rounded-[22px] border border-border bg-card p-5 shadow-sm transition hover:-translate-y-1 hover:border-accent/45 hover:shadow-[var(--shadow-elegant)]"
              >
                <div className="flex items-start justify-between gap-4">
                  <span className="grid h-11 w-11 place-items-center rounded-2xl bg-accent/10 text-accent">
                    <BookOpenCheck className="h-5 w-5" />
                  </span>
                  <span className="font-display text-2xl text-accent">
                    {course.progress_percent}%
                  </span>
                </div>
                <h3 className="mt-5 line-clamp-2 font-display text-2xl leading-tight tracking-tight">
                  {course.topic}
                </h3>
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Layers3 className="h-3.5 w-3.5" />{" "}
                    {course.completed_modules}/{course.total_modules} modules
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock3 className="h-3.5 w-3.5" />{" "}
                    {course.status === "completed"
                      ? "Completed"
                      : "In progress"}
                  </span>
                </div>
                <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-accent transition-all"
                    style={{ width: `${course.progress_percent}%` }}
                  />
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </motion.section>
  );
}
