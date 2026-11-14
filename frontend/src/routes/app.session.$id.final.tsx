import { Link, createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Award,
  CheckCircle2,
  Clock,
  Loader2,
  Lock,
  RotateCcw,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AnswerControl } from "@/components/adaptive-assessment";
import { QuestionResult } from "@/components/assessment-result";
import { ConceptCoachPanel } from "@/components/concept-coach";
import { SessionBackButton } from "@/components/session-back-button";
import {
  apiErrorMessage,
  getCourse,
  getFinalAssessment,
  startFinalAssessment,
  submitFinalAssessment,
  type FinalAssessment,
  type FinalAssessmentState,
} from "@/lib/api";
import { preloadCoursePage } from "@/lib/route-prefetch";

export const Route = createFileRoute("/app/session/$id/final")({
  beforeLoad: ({ context, params }) =>
    preloadCoursePage(context.queryClient, params.id),
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
  }),
  head: () => ({ meta: [{ title: "Final assessment - Lexinit" }] }),
  component: FinalAssessmentPage,
});

type Answer = number | boolean | string | null;

const TYPE_LABELS = {
  mcq: "Multiple choice",
  truefalse: "True or false",
  oneword: "One-word answer",
} as const;

function FinalAssessmentPage() {
  const { id } = Route.useParams();
  const queryClient = useQueryClient();
  const course = useQuery({
    queryKey: ["course", id],
    queryFn: () => getCourse(id),
    staleTime: 5_000,
  });
  const state = course.data?.final_assessment;
  const [finalId, setFinalId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  // Resume an attempt in progress, or show the latest finished one.
  const shownId =
    finalId ?? state?.active_final_id ?? state?.last_final_id ?? null;
  const attempt = useQuery({
    queryKey: ["final-assessment", shownId],
    queryFn: () => getFinalAssessment(shownId!),
    enabled: Boolean(shownId),
    staleTime: 30_000,
  });

  const start = async () => {
    setStarting(true);
    setError("");
    try {
      const started = await startFinalAssessment(id);
      queryClient.setQueryData(["final-assessment", started.final_id], started);
      setFinalId(started.final_id);
      void queryClient.invalidateQueries({ queryKey: ["course", id] });
    } catch (cause) {
      setError(
        apiErrorMessage(cause, "Could not prepare the final assessment."),
      );
    } finally {
      setStarting(false);
    }
  };

  const onSubmitted = (result: FinalAssessment) => {
    queryClient.setQueryData(["final-assessment", result.final_id], result);
    setFinalId(result.final_id);
    for (const queryKey of [
      ["course", id],
      ["courses"],
      ["mastery"],
      ["weak-concepts"],
      ["next-recommendation"],
      ["due-reviews"],
    ]) {
      void queryClient.invalidateQueries({ queryKey });
    }
  };

  const active = attempt.data?.status === "active" ? attempt.data : null;
  const finished = attempt.data?.status === "completed" ? attempt.data : null;

  return (
    <div className="mx-auto max-w-4xl">
      <header className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="flex min-w-0 items-center gap-3">
          <SessionBackButton sessionId={id} />
          <Award className="h-8 w-8 shrink-0 text-accent" />
          <h1 className="min-w-0 font-display text-3xl leading-[1.05] tracking-tight sm:text-4xl">
            Final assessment
          </h1>
        </div>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          {state?.question_count ?? 12} new questions across every module,
          weighted toward the concepts you found hardest. Score{" "}
          {state?.pass_percent ?? 70}% or more to complete the course and earn
          its badge.
        </p>
      </header>

      <div className="mt-4 space-y-4">
        {course.isLoading && <Panel>Loading your progress.</Panel>}
        {course.isError && <Panel>{course.error.message}</Panel>}

        {state && !state.required && (
          <Panel>This course does not have a final assessment.</Panel>
        )}

        {state?.required && !active && (
          <StatusCard
            sessionId={id}
            state={state}
            starting={starting}
            hasResult={Boolean(finished)}
            onStart={() => void start()}
          />
        )}
        {error && (
          <p className="rounded-xl border border-destructive/25 bg-destructive/8 p-4 text-sm text-destructive">
            {error}
          </p>
        )}

        {active && <TakeFinal attempt={active} onSubmitted={onSubmitted} />}
        {finished && <FinalResult attempt={finished} sessionId={id} />}
      </div>
    </div>
  );
}

function StatusCard({
  sessionId,
  state,
  starting,
  hasResult,
  onStart,
}: {
  sessionId: string;
  state: FinalAssessmentState;
  starting: boolean;
  hasResult: boolean;
  onStart: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (state.state !== "cooldown") return;
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, [state.state]);

  if (state.state === "passed") {
    return (
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-accent/30 bg-accent/10 p-5">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-8 w-8 shrink-0 text-accent" />
          <div>
            <h2 className="font-display text-2xl tracking-tight">
              Final assessment passed
            </h2>
            <p className="text-sm text-muted-foreground">
              Best score {state.best_percent}%. Finish any remaining activities
              to complete the course.
            </p>
          </div>
        </div>
        <Link
          to="/app/session/$id/path"
          params={{ id: sessionId }}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
        >
          Course overview <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    );
  }

  if (state.state === "locked") {
    return (
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-3">
          <Lock className="h-6 w-6 shrink-0 text-muted-foreground" />
          <h2 className="font-display text-2xl tracking-tight">
            Pass every module first
          </h2>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          The final unlocks when you have scored 50% or more on each assessment
          in every module. Still to pass:
        </p>
        <ul className="mt-3 space-y-2">
          {(state.modules_remaining ?? []).map((module) => (
            <li key={module.module_id}>
              <Link
                to="/app/session/$id/assessments"
                params={{ id: sessionId }}
                search={{
                  module: module.module_id,
                  submission: undefined,
                  type: undefined,
                  reattempt: undefined,
                }}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/45 px-4 py-3 text-sm font-medium transition hover:bg-muted"
              >
                {module.title}
                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  const retryAt = state.retry_available_at
    ? new Date(state.retry_available_at).getTime()
    : 0;
  const waiting = state.state === "cooldown" && retryAt > now;
  const hours = Math.max(0, Math.floor((retryAt - now) / 3_600_000));
  const minutes = Math.max(
    0,
    Math.ceil(((retryAt - now) % 3_600_000) / 60_000),
  );

  return (
    <section className="rounded-2xl border border-accent/25 bg-accent/10 p-5 sm:p-6">
      <h2 className="font-display text-2xl tracking-tight">
        {state.attempts ? "Retake the final assessment" : "You are ready"}
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
        {waiting
          ? `Use the review plan below to work on what you missed. You can retake the final in ${hours}h ${minutes}m. The wait helps the ideas stick.`
          : "Every attempt uses new questions. Answers are shown after you submit. Preparing the questions takes about half a minute."}
      </p>
      {state.attempts > 0 && state.last_percent !== null && (
        <p className="mt-2 text-sm font-medium">
          Last score {state.last_percent}% · {state.pass_percent}% needed
        </p>
      )}
      <button
        type="button"
        onClick={onStart}
        disabled={starting || waiting}
        className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
      >
        {starting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : waiting ? (
          <Clock className="h-4 w-4" />
        ) : hasResult ? (
          <RotateCcw className="h-4 w-4" />
        ) : (
          <Award className="h-4 w-4" />
        )}
        {starting
          ? "Preparing your questions"
          : waiting
            ? "Retake available later"
            : state.attempts
              ? "Start retake"
              : "Start final assessment"}
      </button>
    </section>
  );
}

function TakeFinal({
  attempt,
  onSubmitted,
}: {
  attempt: FinalAssessment;
  onSubmitted: (result: FinalAssessment) => void;
}) {
  const storageKey = `lexinit:final-answers:${attempt.final_id}`;
  const [answers, setAnswers] = useState<Answer[]>(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
      if (Array.isArray(saved) && saved.length === attempt.questions.length) {
        return saved as Answer[];
      }
    } catch {
      // Saved answers are a convenience; start empty if they cannot be read.
    }
    return attempt.questions.map(() => null);
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(answers));
    } catch {
      // Ignore storage failures; answers stay in memory.
    }
  }, [answers, storageKey]);

  const answered = answers.filter(
    (answer) => answer !== null && answer !== "",
  ).length;
  const complete = answered === attempt.questions.length;

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const result = await submitFinalAssessment(
        attempt.final_id,
        answers.map((answer) =>
          typeof answer === "string" ? answer.trim() : answer,
        ) as Array<number | boolean | string>,
      );
      try {
        window.localStorage.removeItem(storageKey);
      } catch {
        // Nothing to clean up.
      }
      onSubmitted(result);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not submit the final."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4">
      {attempt.questions.map((question, index) => (
        <article
          key={question.index}
          className="rounded-2xl border border-border bg-card p-5 shadow-sm"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Question {index + 1} of {attempt.questions.length} ·{" "}
            {TYPE_LABELS[question.type]}
          </p>
          <h2 className="mt-2 text-lg font-semibold leading-7">
            {question.question}
          </h2>
          <div className="mt-4">
            <AnswerControl
              assessmentType={question.type}
              options={question.options}
              value={answers[index]}
              onChange={(value) =>
                setAnswers((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index ? value : item,
                  ),
                )
              }
            />
          </div>
        </article>
      ))}
      <div className="sticky bottom-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card/95 p-4 shadow-lg backdrop-blur">
        <p className="text-sm text-muted-foreground">
          {answered} of {attempt.questions.length} answered
        </p>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!complete || submitting}
          className="inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Submit final assessment
        </button>
        {error && <p className="w-full text-sm text-destructive">{error}</p>}
      </div>
    </section>
  );
}

function FinalResult({
  attempt,
  sessionId,
}: {
  attempt: FinalAssessment;
  sessionId: string;
}) {
  const result = attempt.result;
  if (!result) return null;
  const missed = result.concepts.filter((concept) => concept.missed > 0);
  return (
    <section className="space-y-4">
      <div
        className={`flex flex-wrap items-center justify-between gap-4 rounded-2xl border p-5 sm:p-6 ${result.passed ? "border-accent/30 bg-accent/10" : "border-destructive/25 bg-destructive/8"}`}
      >
        <div className="flex items-center gap-3">
          <span
            className={`grid h-12 w-12 place-items-center rounded-full ${result.passed ? "bg-accent text-accent-foreground" : "bg-destructive text-destructive-foreground"}`}
          >
            {result.passed ? (
              <Award className="h-6 w-6" />
            ) : (
              <X className="h-6 w-6" />
            )}
          </span>
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              {result.passed
                ? "Passed. You know this course."
                : `Not passed yet. ${result.pass_percent}% needed.`}
            </p>
            <h2 className="font-display text-3xl tracking-tight">
              {result.score} / {result.total}
            </h2>
          </div>
        </div>
        <span
          className={`font-display text-4xl tracking-tight ${result.passed ? "text-accent" : "text-destructive"}`}
        >
          {result.percent}%
        </span>
      </div>

      {missed.length > 0 && (
        <ConceptCoachPanel sessionId={sessionId} concepts={missed} />
      )}

      <div className="space-y-3 rounded-2xl border border-border bg-card p-4 sm:p-5">
        <h3 className="font-display text-xl tracking-tight">Review answers</h3>
        {result.questions.map((question, index) => (
          <QuestionResult
            key={`${attempt.final_id}-${question.index}`}
            question={question}
            index={index}
            assessmentType={question.type}
            sessionId={sessionId}
            report={{ source: "final", referenceId: attempt.final_id }}
          />
        ))}
      </div>
    </section>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground">
      {children}
    </div>
  );
}
