import {
  AlertTriangle,
  Check,
  Loader2,
  RefreshCw,
  Square,
  X,
} from "lucide-react";

import type { GenerationRun, GenerationStage } from "@/lib/api";

const STAGE_LABELS: Record<GenerationStage, string> = {
  queued: "Preparing your course",
  safety: "Reviewing topic",
  cache: "Checking saved courses",
  curriculum: "Learning Path",
  knowledge: "Course foundation",
  materials: "Study Materials",
  practice: "Assessments",
  videos: "Video Lectures",
  learning_path: "Learning Path",
  resources: "Additional Resources",
  saving: "Finalizing course",
  completed: "Complete",
};

export function GenerationProgressCard({
  run,
  busy = false,
  onCancel,
  onRetry,
  onDismiss,
}: {
  run: GenerationRun;
  busy?: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  const failed = run.status === "failed";
  const cancelled = run.status === "cancelled";
  const complete = run.status === "completed";

  return (
    <section
      aria-live="polite"
      className="mx-auto max-w-3xl rounded-[22px] border border-border bg-card p-5 shadow-[var(--shadow-elegant)]"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div
            className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full ${
              failed
                ? "bg-destructive/12 text-destructive"
                : complete
                  ? "bg-accent text-accent-foreground"
                  : "bg-accent/12 text-accent"
            }`}
          >
            {failed ? (
              <AlertTriangle className="h-5 w-5" />
            ) : complete ? (
              <Check className="h-5 w-5" strokeWidth={3} />
            ) : cancelled ? (
              <Square className="h-4 w-4" />
            ) : (
              <Loader2 className="h-5 w-5 animate-spin" />
            )}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
              {STAGE_LABELS[run.stage]}
            </div>
            <h2 className="mt-1 truncate font-display text-xl tracking-tight text-foreground">
              {run.topic || "New course"}
            </h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {run.error?.message || run.message}
            </p>
          </div>
        </div>
        {(failed || cancelled) && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss course creation status"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="mt-5 flex items-center justify-end text-xs font-medium text-muted-foreground [&>span+span]:hidden">
        <span>{run.progress}% complete</span>
        <span>
          {run.completed_steps.length} checkpoints saved · {run.progress}%
        </span>
      </div>
      <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${
            failed ? "bg-destructive" : "bg-accent"
          }`}
          style={{ width: `${run.progress}%` }}
        />
      </div>

      {(run.can_cancel || run.can_retry) && (
        <div className="mt-5 flex flex-wrap gap-2">
          {run.can_retry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={busy}
              className="inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
              Continue course creation
            </button>
          )}
          {run.can_cancel && (
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-border bg-background px-4 text-sm font-semibold text-foreground transition hover:bg-muted disabled:opacity-50"
            >
              <Square className="h-3.5 w-3.5" />
              Cancel generation
            </button>
          )}
        </div>
      )}
    </section>
  );
}
