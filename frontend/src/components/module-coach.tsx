import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Gauge, Loader2 } from "lucide-react";
import { useState } from "react";

import {
  CoachCheckQuestion,
  ConceptCoachPanel,
} from "@/components/concept-coach";
import {
  apiErrorMessage,
  getModuleCoachOverview,
  startPreCheck,
  type ModuleCoachOverview,
} from "@/lib/api";

function useModuleOverview(sessionId: string, moduleId: string) {
  return useQuery({
    queryKey: ["module-coach", sessionId, moduleId],
    queryFn: () => getModuleCoachOverview(sessionId, moduleId),
    staleTime: 15_000,
  });
}

/** A short diagnostic before studying a module, so learners can skip what
 * they already know. */
export function ModulePreCheck({
  sessionId,
  moduleId,
}: {
  sessionId: string;
  moduleId: string;
}) {
  const queryClient = useQueryClient();
  const overview = useModuleOverview(sessionId, moduleId);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{
    done: number;
    correct: number;
  } | null>(null);

  const data = overview.data;
  if (!data || (!data.pre_check_available && !data.pre_check)) return null;
  const preCheck = data.pre_check;
  const total = preCheck?.total ?? Math.min(4, data.concepts.length);
  const done = progress?.done ?? preCheck?.answered ?? 0;
  const correct = progress?.correct ?? preCheck?.correct ?? 0;
  const finished = Boolean(preCheck) && done >= total;
  // A finished pre-check is only a summary; hide it once collapsed.
  if (finished && !open && !progress) return null;

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const created = await startPreCheck(sessionId, moduleId);
      queryClient.setQueryData<ModuleCoachOverview>(
        ["module-coach", sessionId, moduleId],
        { ...data, pre_check_available: false, pre_check: created },
      );
      setOpen(true);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not prepare the pre-check."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-6 rounded-2xl border border-accent/25 bg-accent/5 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <Gauge className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div className="min-w-0">
            <h3 className="font-semibold">
              {finished
                ? `Pre-check: ${correct} of ${total} correct`
                : "Already know some of this?"}
            </h3>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {finished
                ? correct === total
                  ? "You already know this module. Skim the material or go straight to the assessment."
                  : "Focus on the concepts you missed as you read. The others you can skim."
                : `Take a ${total}-question pre-check to see what you can skip. About 2 minutes.`}
            </p>
          </div>
        </div>
        {!preCheck && (
          <button
            type="button"
            onClick={() => void start()}
            disabled={busy}
            className="inline-flex h-9 shrink-0 items-center gap-2 rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-60"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {busy ? "Preparing" : "Take pre-check"}
          </button>
        )}
        {preCheck && !open && !finished && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex h-9 shrink-0 items-center rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground transition hover:opacity-90"
          >
            Continue pre-check
          </button>
        )}
        {finished && correct === total && (
          <Link
            to="/app/session/$id/assessments"
            params={{ id: sessionId }}
            search={{
              module: moduleId,
              submission: undefined,
              type: undefined,
              reattempt: undefined,
            }}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground transition hover:opacity-90"
          >
            Go to assessment <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      {preCheck && open && (
        <div className="mt-4 space-y-5 border-t border-accent/15 pt-4">
          {preCheck.checks.map((check, index) => (
            <div key={check.check_id}>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {index + 1} · {check.concept_label}
              </p>
              <CoachCheckQuestion
                check={check}
                sessionId={sessionId}
                onAnswered={(result) => {
                  setProgress((current) => ({
                    done: (current?.done ?? preCheck.answered) + 1,
                    correct:
                      (current?.correct ?? preCheck.correct) +
                      (result.correct ? 1 : 0),
                  }));
                  void queryClient.invalidateQueries({
                    queryKey: ["module-coach", sessionId, moduleId],
                  });
                }}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/** Per-concept help under the study material: another explanation or a few
 * practice questions, for any concept in the module. */
export function ModuleConceptCoach({
  sessionId,
  moduleId,
}: {
  sessionId: string;
  moduleId: string;
}) {
  const overview = useModuleOverview(sessionId, moduleId);
  if (!overview.data?.concepts.length) return null;
  // Weakest concepts first; ones not practised yet come before strong ones.
  const concepts = [...overview.data.concepts].sort(
    (left, right) =>
      (left.current_mastery ?? 0.5) - (right.current_mastery ?? 0.5),
  );
  return (
    <div className="mt-8">
      <ConceptCoachPanel
        sessionId={sessionId}
        concepts={concepts}
        title="Stuck on a concept?"
        description="Get it explained a different way, or try a few practice questions. Your weakest concepts are listed first."
      />
    </div>
  );
}
