import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  Eye,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";

import {
  apiErrorMessage,
  createIdempotencyKey,
  getDueReviews,
  recordReview,
  type ReviewRating,
} from "@/lib/api";

export const Route = createFileRoute("/app/reviews")({
  head: () => ({ meta: [{ title: "Review queue - Lexinit" }] }),
  component: ReviewQueue,
});

const RATINGS: Array<{
  value: ReviewRating;
  label: string;
  detail: string;
}> = [
  { value: "again", label: "Again", detail: "Review tomorrow" },
  { value: "hard", label: "Hard", detail: "Short interval" },
  { value: "good", label: "Good", detail: "About a week" },
  { value: "easy", label: "Easy", detail: "Longer interval" },
];

function ReviewQueue() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["due-reviews"],
    queryFn: () => getDueReviews(20),
  });
  const [revealed, setRevealed] = useState(false);
  const [submitting, setSubmitting] = useState<ReviewRating | null>(null);
  const [error, setError] = useState("");
  const current = query.data?.reviews[0];

  const rate = async (rating: ReviewRating) => {
    if (!current) return;
    setSubmitting(rating);
    setError("");
    try {
      const keyStorage = `lexinit:review-key:${current.review_id}:${rating}`;
      let idempotencyKey = window.localStorage.getItem(keyStorage);
      if (!idempotencyKey) {
        idempotencyKey = createIdempotencyKey(`review-${current.concept_id}`);
        window.localStorage.setItem(keyStorage, idempotencyKey);
      }
      await recordReview(
        {
          concept_id: current.concept_id,
          session_id: current.session_id,
          artifact_id: current.artifact.artifact_id,
          rating,
        },
        idempotencyKey,
      );
      window.localStorage.removeItem(keyStorage);
      setRevealed(false);
      await Promise.all([
        query.refetch(),
        queryClient.invalidateQueries({ queryKey: ["mastery"] }),
        queryClient.invalidateQueries({ queryKey: ["weak-concepts"] }),
        queryClient.invalidateQueries({ queryKey: ["next-recommendation"] }),
      ]);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not save this review."));
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <Link
          to="/app"
          className="inline-flex h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Progress
        </Link>
        <div className="mt-5 flex items-center gap-3 text-accent">
          <BrainCircuit className="h-5 w-5" />
          <span className="text-sm font-semibold uppercase tracking-[0.16em]">
            Smart review
          </span>
        </div>
        <h1 className="mt-2 font-display text-4xl tracking-tight sm:text-5xl">
          Review queue
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Rate how well you remembered each concept. Your next review date will
          adjust to give you more practice where you need it.
        </p>
      </header>

      {query.isLoading && (
        <div className="grid min-h-72 place-items-center rounded-2xl border border-border bg-card">
          <Loader2 className="h-7 w-7 animate-spin text-accent" />
        </div>
      )}

      {query.isError && (
        <div className="rounded-2xl border border-destructive/25 bg-destructive/5 p-5">
          <p className="text-sm text-destructive">
            {apiErrorMessage(query.error, "Could not load your review queue.")}
          </p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="mt-3 inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium"
          >
            <RefreshCw className="h-4 w-4" /> Retry
          </button>
        </div>
      )}

      {!query.isLoading && !query.isError && !current && (
        <div className="rounded-2xl border border-border bg-card p-8 text-center shadow-sm">
          <CheckCircle2 className="mx-auto h-10 w-10 text-accent" />
          <h2 className="mt-4 font-display text-3xl tracking-tight">
            All caught up
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Your next review will appear here when it is due.
          </p>
        </div>
      )}

      {current && (
        <article className="overflow-hidden rounded-[24px] border border-border bg-card shadow-[var(--shadow-elegant)]">
          <div className="border-b border-border p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
                  {current.concept_label}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {query.data?.due_count ?? 0} review
                  {(query.data?.due_count ?? 0) === 1 ? "" : "s"} due
                </div>
              </div>
              <span className="rounded-full bg-accent/10 px-3 py-1 text-xs font-semibold capitalize text-accent">
                {current.band} · {Math.round(current.mastery_probability * 100)}
                %
              </span>
            </div>
          </div>
          <div className="p-6 sm:p-8">
            <h2 className="font-display text-3xl leading-tight tracking-tight">
              {current.artifact.prompt}
            </h2>
            {!revealed ? (
              <button
                type="button"
                onClick={() => setRevealed(true)}
                className="mt-8 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground"
              >
                <Eye className="h-4 w-4" /> Reveal and rate recall
              </button>
            ) : (
              <div className="mt-8 space-y-5">
                <div className="rounded-xl border border-accent/25 bg-accent/10 p-5 text-sm leading-7">
                  {current.artifact.answer ||
                    "Compare your explanation with the study material, then rate how confidently you recalled it."}
                </div>
                <div className="grid gap-2 sm:grid-cols-4">
                  {RATINGS.map((rating) => (
                    <button
                      key={rating.value}
                      type="button"
                      onClick={() => void rate(rating.value)}
                      disabled={Boolean(submitting)}
                      className="rounded-xl border border-border bg-background/50 p-3 text-left transition hover:border-accent/40 hover:bg-accent/10 disabled:opacity-50"
                    >
                      <span className="block font-semibold">
                        {rating.label}
                      </span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {rating.detail}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
          </div>
        </article>
      )}
    </div>
  );
}
