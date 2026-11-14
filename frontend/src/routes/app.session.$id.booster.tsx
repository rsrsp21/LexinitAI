import { Link, createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Loader2, Zap } from "lucide-react";
import { useState } from "react";

import { CoachCheckQuestion } from "@/components/concept-coach";
import { MarkdownContent } from "@/components/markdown-content";
import { SessionBackButton } from "@/components/session-back-button";
import {
  apiErrorMessage,
  createBooster,
  getBoosterStatus,
  type Booster,
  type BoosterStatus,
} from "@/lib/api";

export const Route = createFileRoute("/app/session/$id/booster")({
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
  }),
  head: () => ({ meta: [{ title: "Booster - Lexinit" }] }),
  component: BoosterPage,
});

function percent(value: number | null) {
  return value === null ? "not practised" : `${Math.round(value * 100)}%`;
}

function BoosterPage() {
  const { id } = Route.useParams();
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["booster", id],
    queryFn: () => getBoosterStatus(id),
    staleTime: 10_000,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = () => {
    for (const queryKey of [
      ["booster", id],
      ["course", id],
      ["course-mastery", id],
      ["mastery"],
      ["weak-concepts"],
      ["knowledge-map"],
    ]) {
      void queryClient.invalidateQueries({ queryKey });
    }
  };

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const booster = await createBooster(id);
      queryClient.setQueryData<BoosterStatus>(["booster", id], (current) =>
        current ? { ...current, booster } : current,
      );
      void queryClient.invalidateQueries({ queryKey: ["booster", id] });
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not prepare the booster."));
    } finally {
      setBusy(false);
    }
  };

  const data = status.data;
  const booster = data?.booster ?? null;
  const open = booster && !booster.completed ? booster : null;
  const canStart = Boolean(data?.eligible) && (data?.remaining_today ?? 0) > 0;

  return (
    <div className="mx-auto max-w-4xl">
      <header className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="flex min-w-0 items-center gap-3">
          <SessionBackButton sessionId={id} />
          <Zap className="h-8 w-8 shrink-0 text-accent" />
          <h1 className="min-w-0 font-display text-3xl leading-[1.05] tracking-tight sm:text-4xl">
            Booster
          </h1>
        </div>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          A short lesson and five questions on the concepts you are still
          getting wrong. It takes about ten minutes, stays inside this course,
          and does not use your daily course generations.
        </p>
      </header>

      <div className="mt-4 space-y-4">
        {status.isLoading && <Panel>Checking your progress.</Panel>}
        {status.isError && <Panel>{status.error.message}</Panel>}

        {data && !open && (
          <section className="rounded-2xl border border-accent/25 bg-accent/10 p-5 sm:p-6">
            {data.eligible ? (
              <>
                <h2 className="font-display text-2xl tracking-tight">
                  {booster ? "Another booster is ready" : "Ready when you are"}
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  These concepts are still weak after several answers:
                </p>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {data.concepts.map((concept) => (
                    <li
                      key={concept.concept_id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/60 px-4 py-2.5"
                    >
                      <span className="font-medium">
                        {concept.concept_label}
                      </span>
                      <span className="text-muted-foreground">
                        {percent(concept.current_mastery)} mastery
                      </span>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => void start()}
                  disabled={busy || !canStart}
                  className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Zap className="h-4 w-4" />
                  )}
                  {busy ? "Writing your booster" : "Start booster"}
                </button>
                <p className="mt-2 text-xs text-muted-foreground">
                  {data.remaining_today > 0
                    ? `${data.remaining_today} of ${data.daily_limit} boosters left today. Writing one takes about half a minute.`
                    : `You have used today's ${data.daily_limit} boosters. Come back tomorrow.`}
                </p>
              </>
            ) : (
              <>
                <h2 className="font-display text-2xl tracking-tight">
                  No booster needed right now
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  A booster appears when a concept stays below 50% mastery after
                  at least three answers. Keep working through the assessments;
                  quick fixes and practice are on every result.
                </p>
              </>
            )}
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </section>
        )}

        {booster && (
          <BoosterView
            key={booster.booster_id}
            booster={booster}
            sessionId={id}
            onAnswered={refresh}
          />
        )}
      </div>
    </div>
  );
}

function BoosterView({
  booster,
  sessionId,
  onAnswered,
}: {
  booster: Booster;
  sessionId: string;
  onAnswered: () => void;
}) {
  return (
    <>
      {booster.completed && (
        <section
          className={`rounded-2xl border p-5 sm:p-6 ${booster.gap_closed ? "border-accent/30 bg-accent/10" : "border-border bg-card"}`}
        >
          <div className="flex items-center gap-3">
            <CheckCircle2
              className={`h-7 w-7 shrink-0 ${booster.gap_closed ? "text-accent" : "text-muted-foreground"}`}
            />
            <div>
              <h2 className="font-display text-2xl tracking-tight">
                {booster.gap_closed
                  ? "Gap closed"
                  : "Not there yet, but closer"}
              </h2>
              <p className="text-sm text-muted-foreground">
                {booster.correct} of {booster.total} correct.{" "}
                {booster.gap_closed
                  ? "These concepts will come back in your daily mix so they stick."
                  : "Reread the lesson below, then use Explain differently on the study material."}
              </p>
            </div>
          </div>
          <ul className="mt-4 grid gap-2 sm:grid-cols-2">
            {booster.concepts.map((concept) => (
              <li
                key={concept.concept_id}
                className="rounded-xl border border-border bg-background/60 px-4 py-3 text-sm"
              >
                <span className="block font-medium">
                  {concept.concept_label}
                </span>
                <span className="text-muted-foreground">
                  {percent(concept.mastery_before)} before, now{" "}
                  {percent(concept.current_mastery)}
                </span>
              </li>
            ))}
          </ul>
          <Link
            to="/app/session/$id/path"
            params={{ id: sessionId }}
            className="mt-4 inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
          >
            Back to the course <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      )}

      <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7">
        <h2 className="font-display text-2xl tracking-tight">
          {booster.title}
        </h2>
        <div className="mt-4 text-sm leading-7">
          <MarkdownContent content={booster.lesson} />
        </div>
        {booster.key_points.length > 0 && (
          <div className="mt-5 rounded-xl bg-muted/60 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Key points
            </h3>
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-6">
              {booster.key_points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7">
        <div>
          <h2 className="font-display text-2xl tracking-tight">
            Check you have it now
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {booster.answered} of {booster.total} answered. Score{" "}
            {booster.pass_percent}% or more to close the gap.
          </p>
        </div>
        {booster.checks.map((check, index) => (
          <article
            key={check.check_id}
            className="rounded-xl border border-border bg-background/45 p-4"
          >
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {index + 1} · {check.concept_label} · {check.difficulty}
            </p>
            <CoachCheckQuestion
              check={check}
              sessionId={sessionId}
              onAnswered={onAnswered}
            />
          </article>
        ))}
      </section>
    </>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground">
      {children}
    </div>
  );
}
