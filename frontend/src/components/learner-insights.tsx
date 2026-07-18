import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BrainCircuit,
  CalendarClock,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import {
  ApiError,
  apiErrorMessage,
  createIdempotencyKey,
  generateFromRecommendation,
  getDueReviews,
  getNextRecommendation,
  getWeakConcepts,
  type MasteryBand,
} from "@/lib/api";

const BAND_LABELS: Record<MasteryBand, string> = {
  weak: "Needs focus",
  developing: "Developing",
  proficient: "Proficient",
  mastered: "Mastered",
};

const NEXT_ACTION_LABELS: Record<string, string> = {
  prerequisite_remediation: "Review the basics",
  misconception_correction: "Clear up a misunderstanding",
  weak_topic_remediation: "Strengthen the foundation",
  targeted_practice: "Continue focused practice",
  application_practice: "Apply the concept",
  difficulty_progression: "Try a harder level",
  spaced_review: "Review this concept",
};

function reviewLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Review soon";
  const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return "Review due";
  if (days === 1) return "Review tomorrow";
  return `Review in ${days} days`;
}

export function LearnerInsights() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [startingRecommendation, setStartingRecommendation] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const query = useQuery({
    queryKey: ["weak-concepts"],
    queryFn: () => getWeakConcepts(6),
    staleTime: 30_000,
    retry: false,
  });
  const recommendationQuery = useQuery({
    queryKey: ["next-recommendation"],
    queryFn: getNextRecommendation,
    staleTime: 20_000,
  });
  const reviewsQuery = useQuery({
    queryKey: ["due-reviews", "summary"],
    queryFn: () => getDueReviews(1),
    staleTime: 20_000,
  });
  const recommendation = recommendationQuery.data?.recommendation;

  const startRecommendation = async () => {
    if (!recommendation?.decision_id) return;
    setStartingRecommendation(true);
    setRecommendationError("");
    try {
      const result = await generateFromRecommendation(
        recommendation.decision_id,
        createIdempotencyKey("adaptive-generation"),
      );
      if (!result.job_id)
        throw new Error(
          "The focused course was not created. Please try again.",
        );
      window.localStorage.setItem(
        "lexinit:generation:new-session",
        result.job_id,
      );
      await queryClient.invalidateQueries({
        queryKey: ["generation-runs", "active"],
      });
      navigate({ to: "/app/new-course" });
    } catch (cause) {
      setRecommendationError(
        apiErrorMessage(cause, "Could not create the recommended course."),
      );
    } finally {
      setStartingRecommendation(false);
    }
  };

  return (
    <section
      aria-labelledby="learner-insights-title"
      className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2
            id="learner-insights-title"
            className="flex items-center gap-2 font-display text-2xl tracking-tight sm:text-3xl"
          >
            <BrainCircuit className="h-6 w-6 shrink-0 text-accent" />
            Concepts to strengthen
          </h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Based on your recent assessment results.
          </p>
        </div>
        {query.isFetching && (
          <RefreshCw
            className="h-4 w-4 animate-spin text-muted-foreground"
            aria-label="Refreshing recommended next steps"
          />
        )}
      </div>

      {(recommendation || (reviewsQuery.data?.due_count || 0) > 0) && (
        <div className="mt-5 rounded-2xl border border-accent/30 bg-accent/10 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-accent">
                <Sparkles className="h-4 w-4" /> Recommended next
              </div>
              <h3 className="mt-2 font-display text-2xl tracking-tight">
                {(reviewsQuery.data?.due_count || 0) > 0
                  ? "A spaced review is due"
                  : recommendation?.concept_label}
              </h3>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {(reviewsQuery.data?.due_count || 0) > 0
                  ? "A quick review now will help this concept stay fresh."
                  : `${NEXT_ACTION_LABELS[recommendation?.action || ""] || "Continue focused practice"} at the ${recommendation?.target_difficulty} level.`}
              </p>
            </div>
            {(reviewsQuery.data?.due_count || 0) > 0 ? (
              <Link
                to="/app/reviews"
                className="inline-flex h-10 shrink-0 items-center justify-center rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground"
              >
                Open review queue
              </Link>
            ) : recommendation?.can_generate && recommendation.decision_id ? (
              <button
                type="button"
                onClick={() => void startRecommendation()}
                disabled={startingRecommendation}
                className="inline-flex h-10 shrink-0 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
              >
                {startingRecommendation && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                Create focused course
              </button>
            ) : null}
          </div>
          {recommendationError && (
            <p className="mt-3 text-sm text-destructive">
              {recommendationError}
            </p>
          )}
        </div>
      )}

      {query.isLoading && (
        <div
          className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
          aria-label="Loading recommended next steps"
        >
          {[0, 1, 2].map((item) => (
            <div
              key={item}
              className="h-32 animate-pulse rounded-xl bg-muted"
            />
          ))}
        </div>
      )}

      {query.isError && (
        <div className="mt-5 flex flex-col gap-3 rounded-xl border border-destructive/25 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="text-sm">
              <p className="font-medium text-foreground">
                Could not load recommended next steps
              </p>
              <p className="mt-1 text-muted-foreground">
                {query.error instanceof Error
                  ? query.error.message
                  : "Try again in a moment."}
              </p>
              {query.error instanceof ApiError && query.error.requestId && (
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  Support code: {query.error.requestId}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium transition hover:bg-muted"
          >
            <RefreshCw className="h-4 w-4" /> Retry
          </button>
        </div>
      )}

      {!query.isLoading &&
        !query.isError &&
        query.data?.weak_concepts.length === 0 && (
          <div className="mt-5 rounded-xl border border-border bg-background/50 p-5 text-sm leading-6 text-muted-foreground">
            Complete an assessment to start building your learning profile.
            Personalized suggestions will appear here as you practise.
          </div>
        )}

      {query.data && query.data.weak_concepts.length > 0 && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.weak_concepts.map((concept) => {
            const percentage = Math.round(concept.mastery_probability * 100);
            return (
              <article
                key={concept.concept_id}
                className="rounded-xl border border-border bg-background/55 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold text-foreground">
                      {concept.concept_label}
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {BAND_LABELS[concept.band]} · {concept.attempts} attempt
                      {concept.attempts === 1 ? "" : "s"}
                    </p>
                  </div>
                  <span className="rounded-full bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent">
                    {percentage}%
                  </span>
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
                <div className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <CalendarClock className="h-3.5 w-3.5" />{" "}
                  {reviewLabel(concept.next_review_at)}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
