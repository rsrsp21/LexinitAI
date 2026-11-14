import { CalendarClock, Loader2 } from "lucide-react";
import { useState } from "react";

import {
  apiErrorMessage,
  setCourseGoal,
  type CourseGoal,
  type CourseProgress,
} from "@/lib/api";

function formatDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatMinutes(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

function goalMessage(goal: CourseGoal) {
  if (goal.status === "done") return "Course complete. Goal reached.";
  if (goal.status === "overdue") {
    return `The target date has passed with ${formatMinutes(goal.remaining_minutes)} of study left. Pick a new date.`;
  }
  const days =
    goal.days_left === 0
      ? "today"
      : `in ${goal.days_left} day${goal.days_left === 1 ? "" : "s"}`;
  const pace = `About ${formatMinutes(goal.minutes_per_day)} a day to finish ${days}.`;
  return goal.status === "tight"
    ? `${pace} That is a heavy pace; consider a later date.`
    : pace;
}

/** A target date for the course, turned into a daily study pace from what is
 * actually left to do. */
export function CourseGoalCard({
  sessionId,
  goal,
  onChange,
}: {
  sessionId: string;
  goal: CourseGoal | null | undefined;
  onChange: (course: CourseProgress) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [date, setDate] = useState(goal?.target_date ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  const save = async (value: string | null) => {
    setBusy(true);
    setError("");
    try {
      onChange(await setCourseGoal(sessionId, value));
      setEditing(false);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not save this goal."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative mt-5 rounded-2xl border border-border bg-background/45 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <CalendarClock
            className={`mt-0.5 h-5 w-5 shrink-0 ${goal?.status === "overdue" || goal?.status === "tight" ? "text-amber-600 dark:text-amber-300" : "text-accent"}`}
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold">
              {goal
                ? `Goal: finish by ${formatDate(goal.target_date)}`
                : "Set a finish date"}
            </p>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {goal
                ? goalMessage(goal)
                : "Have an exam or interview coming up? Pick a date and get a daily study pace."}
            </p>
            {goal?.focus_module_title && goal.status !== "done" && (
              <p className="mt-0.5 text-sm text-muted-foreground">
                Today: {goal.focus_module_title}
              </p>
            )}
          </div>
        </div>
        {!editing && (
          <button
            type="button"
            onClick={() => {
              setDate(goal?.target_date ?? "");
              setEditing(true);
            }}
            className="inline-flex h-9 shrink-0 items-center rounded-full border border-border bg-card px-4 text-xs font-semibold transition hover:bg-muted"
          >
            {goal ? "Change" : "Set date"}
          </button>
        )}
      </div>
      {editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
          <label className="sr-only" htmlFor="course-goal-date">
            Finish date
          </label>
          <input
            id="course-goal-date"
            type="date"
            min={today}
            value={date}
            onChange={(event) => setDate(event.target.value)}
            className="h-9 rounded-full border border-border bg-background px-3 text-sm outline-none transition focus:border-accent"
          />
          <button
            type="button"
            onClick={() => void save(date)}
            disabled={!date || busy}
            className="inline-flex h-9 items-center gap-2 rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save
          </button>
          {goal && (
            <button
              type="button"
              onClick={() => void save(null)}
              disabled={busy}
              className="h-9 rounded-full px-3 text-xs font-semibold text-muted-foreground transition hover:bg-muted"
            >
              Remove goal
            </button>
          )}
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="h-9 rounded-full px-3 text-xs font-semibold text-muted-foreground transition hover:bg-muted"
          >
            Cancel
          </button>
          {error && <p className="w-full text-sm text-destructive">{error}</p>}
        </div>
      )}
    </div>
  );
}
