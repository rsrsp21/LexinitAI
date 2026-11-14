import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";

import { CoachCheckQuestion } from "@/components/concept-coach";
import {
  apiErrorMessage,
  getDailyMix,
  startDailyMix,
  type DailyMix,
} from "@/lib/api";

/** A short daily review drawn from every course: concepts due for review
 * first, then the weakest ones. */
export function DailyMixCard() {
  const queryClient = useQueryClient();
  const mix = useQuery({
    queryKey: ["daily-mix"],
    queryFn: getDailyMix,
    staleTime: 60_000,
  });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [score, setScore] = useState<{ done: number; correct: number } | null>(
    null,
  );

  const data = mix.data;
  if (!data) return null;
  const waiting = data.waiting_concepts ?? 0;
  if (!data.ready && waiting === 0) return null;

  const total = data.total ?? data.checks.length;
  const done = score?.done ?? data.answered ?? 0;
  const correct = score?.correct ?? data.correct ?? 0;
  const finished = data.ready && done >= total;

  const start = async () => {
    setError("");
    if (data.ready) {
      setOpen(true);
      return;
    }
    setBusy(true);
    try {
      const created = await startDailyMix();
      queryClient.setQueryData<DailyMix>(["daily-mix"], created);
      setOpen(true);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not prepare today's mix."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-[24px] border border-accent/25 bg-accent/5 p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
            {finished ? (
              <CheckCircle2 className="h-5 w-5" />
            ) : (
              <CalendarCheck className="h-5 w-5" />
            )}
          </span>
          <div className="min-w-0">
            <h2 className="font-display text-2xl tracking-tight">Daily mix</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {finished
                ? `Done for today: ${correct} of ${total} correct. Come back tomorrow.`
                : data.ready
                  ? `${done} of ${total} answered. Pick up where you left off.`
                  : `${Math.min(5, waiting)} quick questions from your courses${
                      data.due_concepts
                        ? `, including ${data.due_concepts} due for review`
                        : ""
                    }. About 5 minutes.`}
            </p>
          </div>
        </div>
        {!open && (
          <button
            type="button"
            onClick={() => void start()}
            disabled={busy}
            className="inline-flex h-11 shrink-0 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-60"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy
              ? "Preparing"
              : finished
                ? "Review answers"
                : data.ready
                  ? "Continue"
                  : "Start today's mix"}
          </button>
        )}
      </div>
      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

      {open && data.ready && (
        <div className="mt-5 space-y-5 border-t border-accent/15 pt-5">
          {data.checks.map((check, index) => (
            <article
              key={check.check_id}
              className="rounded-xl border border-border bg-card p-4"
            >
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {index + 1} · {check.concept_label}
                <span className="font-medium normal-case tracking-normal">
                  {" "}
                  · {check.course_topic} ·{" "}
                  {check.reason === "due" ? "due for review" : "needs work"}
                </span>
              </p>
              <CoachCheckQuestion
                check={check}
                sessionId={check.session_id}
                onAnswered={(result) => {
                  setScore((current) => ({
                    done: (current?.done ?? data.answered ?? 0) + 1,
                    correct:
                      (current?.correct ?? data.correct ?? 0) +
                      (result.correct ? 1 : 0),
                  }));
                  void queryClient.invalidateQueries({
                    queryKey: ["daily-mix"],
                  });
                }}
              />
            </article>
          ))}
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="text-sm font-semibold text-accent hover:underline"
          >
            Close
          </button>
        </div>
      )}
    </section>
  );
}
