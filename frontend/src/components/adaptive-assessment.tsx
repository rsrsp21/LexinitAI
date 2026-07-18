import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BrainCircuit,
  Loader2,
  LockKeyhole,
  Send,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  answerAssessmentAttempt,
  apiErrorMessage,
  createIdempotencyKey,
  finalizeAssessmentAttempt,
  getAssessmentAttempt,
  startAssessmentAttempt,
  type AssessmentAttempt,
  type AssessmentType,
  type SubmitAssessmentResult,
} from "@/lib/api";
import { AssessmentResult } from "@/components/assessment-result";

type Answer = number | boolean | string | null;

export function AdaptiveAssessment({
  sessionId,
  assessmentType,
  availableQuestions,
  moduleId,
  forceNewToken,
}: {
  sessionId: string;
  assessmentType: AssessmentType;
  availableQuestions: number;
  moduleId?: string;
  forceNewToken?: string;
}) {
  const storageKey = `lexinit:assessment-attempt:${sessionId}:${assessmentType}:${moduleId || "all"}`;
  const startKeyStorage = `${storageKey}:start-key`;
  const finalizeKeyStorage = `${storageKey}:finalize-key`;
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(null);
  const [result, setResult] = useState<SubmitAssessmentResult | null>(null);
  const [answer, setAnswer] = useState<Answer>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const queryClient = useQueryClient();
  const question = attempt?.current_question;
  const answeredLabel = useMemo(
    () =>
      attempt
        ? `${Math.min(attempt.answered_count + (question ? 1 : 0), attempt.target_count)} of ${attempt.target_count}`
        : "",
    [attempt, question],
  );

  useEffect(() => {
    if (forceNewToken) {
      window.localStorage.removeItem(storageKey);
      window.localStorage.removeItem(startKeyStorage);
      window.localStorage.removeItem(finalizeKeyStorage);
      setAttempt(null);
      setResult(null);
      return;
    }
    const attemptId = window.localStorage.getItem(storageKey);
    if (!attemptId) return;
    setLoading(true);
    getAssessmentAttempt(attemptId)
      .then((restored) => {
        setAttempt(restored);
        setResult(restored.public_result || null);
      })
      .catch(() => {
        window.localStorage.removeItem(storageKey);
        window.localStorage.removeItem(startKeyStorage);
        window.localStorage.removeItem(finalizeKeyStorage);
      })
      .finally(() => setLoading(false));
  }, [finalizeKeyStorage, forceNewToken, startKeyStorage, storageKey]);

  useEffect(() => {
    setAnswer(null);
  }, [question?.question_id]);

  const start = async () => {
    setLoading(true);
    setError("");
    try {
      let startKey = window.localStorage.getItem(startKeyStorage);
      if (!startKey) {
        startKey = createIdempotencyKey("assessment-start");
        window.localStorage.setItem(startKeyStorage, startKey);
      }
      const started = await startAssessmentAttempt(
        sessionId,
        assessmentType,
        startKey,
        Math.min(5, availableQuestions),
        moduleId,
      );
      window.localStorage.setItem(storageKey, started.attempt_id);
      setAttempt(started);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not start the assessment."));
    } finally {
      setLoading(false);
    }
  };

  const submitAnswer = async () => {
    if (!attempt || !question || answer === null || answer === "") {
      setError("Choose or enter an answer before continuing.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const answerKeyStorage = `${storageKey}:answer-key:${question.question_id}`;
      let answerKey = window.localStorage.getItem(answerKeyStorage);
      if (!answerKey) {
        answerKey = createIdempotencyKey(
          `assessment-answer-${attempt.answered_count + 1}`,
        );
        window.localStorage.setItem(answerKeyStorage, answerKey);
      }
      const updated = await answerAssessmentAttempt(
        attempt.attempt_id,
        question.question_id,
        answer,
        answerKey,
      );
      window.localStorage.removeItem(answerKeyStorage);
      setAttempt(updated);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not save this answer."));
    } finally {
      setLoading(false);
    }
  };

  const finalize = async () => {
    if (!attempt) return;
    setLoading(true);
    setError("");
    try {
      let finalizeKey = window.localStorage.getItem(finalizeKeyStorage);
      if (!finalizeKey) {
        finalizeKey = createIdempotencyKey("assessment-finalize");
        window.localStorage.setItem(finalizeKeyStorage, finalizeKey);
      }
      const submission = await finalizeAssessmentAttempt(
        attempt.attempt_id,
        attempt.submission_token,
        finalizeKey,
      );
      setResult(submission);
      setAttempt({
        ...attempt,
        status: "completed",
        public_result: submission,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["mastery"] }),
        queryClient.invalidateQueries({ queryKey: ["weak-concepts"] }),
        queryClient.invalidateQueries({ queryKey: ["next-recommendation"] }),
        queryClient.invalidateQueries({ queryKey: ["due-reviews"] }),
      ]);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not submit this assessment."));
    } finally {
      setLoading(false);
    }
  };

  if (!availableQuestions) {
    return (
      <p className="text-sm text-muted-foreground">No questions available.</p>
    );
  }

  if (result) {
    return (
      <AssessmentResult
        submissionId={result.submission_id}
        sessionId={sessionId}
        moduleId={moduleId}
      />
    );
  }

  if (!attempt) {
    return (
      <div className="rounded-2xl border border-accent/25 bg-accent/10 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
            <BrainCircuit className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-display text-2xl tracking-tight">Assessment</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Questions appear one at a time and adjust to how you are doing.
              Answers are shown after you finish.
            </p>
            <button
              type="button"
              onClick={() => void start()}
              disabled={loading}
              className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <LockKeyhole className="h-4 w-4" />
              )}
              Start assessment
            </button>
          </div>
        </div>
        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      </div>
    );
  }

  if (attempt.status === "ready") {
    return (
      <div className="rounded-2xl border border-accent/30 bg-accent/10 p-6 text-center">
        <Send className="mx-auto h-8 w-8 text-accent" />
        <h3 className="mt-3 font-display text-2xl tracking-tight">
          All assigned questions answered
        </h3>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          Submit your answers to see the result, update your learning profile,
          and get a recommended next step.
        </p>
        <button
          type="button"
          onClick={() => void finalize()}
          disabled={loading}
          className="mt-5 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          Submit assessment
        </button>
        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="font-medium text-muted-foreground">
          Question {answeredLabel}
        </span>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-border bg-background px-3 py-1 text-xs capitalize">
            {question?.difficulty} difficulty
          </span>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <LockKeyhole className="h-3.5 w-3.5" /> Answers shown when finished
          </span>
        </div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-300"
          style={{
            width: `${((attempt.answered_count + 1) / attempt.target_count) * 100}%`,
          }}
        />
      </div>
      <p className="rounded-xl bg-muted/60 px-4 py-3 text-xs leading-5 text-muted-foreground">
        {attempt.selection_reason}
      </p>
      <h3 className="font-display text-2xl leading-tight tracking-tight sm:text-3xl">
        {question?.question}
      </h3>
      <AnswerControl
        assessmentType={assessmentType}
        options={question?.options || []}
        value={answer}
        onChange={setAnswer}
      />
      <button
        type="button"
        onClick={() => void submitAnswer()}
        disabled={loading || answer === null || answer === ""}
        className="inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <ArrowRight className="h-4 w-4" />
        )}
        Save answer and continue
      </button>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

function AnswerControl({
  assessmentType,
  options,
  value,
  onChange,
}: {
  assessmentType: AssessmentType;
  options: string[];
  value: Answer;
  onChange: (answer: Answer) => void;
}) {
  if (assessmentType === "mcq") {
    return (
      <div className="grid gap-2">
        {options.map((option, index) => (
          <button
            key={`${index}-${option}`}
            type="button"
            onClick={() => onChange(index)}
            className={`rounded-xl border p-4 text-left text-sm transition ${
              value === index
                ? "border-accent bg-accent/10 text-foreground"
                : "border-border bg-background/45 hover:bg-muted"
            }`}
          >
            <span className="mr-3 font-semibold text-accent">
              {String.fromCharCode(65 + index)}
            </span>
            {option}
          </button>
        ))}
      </div>
    );
  }
  if (assessmentType === "truefalse") {
    return (
      <div className="grid grid-cols-2 gap-3">
        {[true, false].map((option) => (
          <button
            key={String(option)}
            type="button"
            onClick={() => onChange(option)}
            className={`rounded-xl border p-4 font-medium transition ${
              value === option
                ? "border-accent bg-accent/10"
                : "border-border bg-background/45 hover:bg-muted"
            }`}
          >
            {option ? "True" : "False"}
          </button>
        ))}
      </div>
    );
  }
  return (
    <input
      value={typeof value === "string" ? value : ""}
      onChange={(event) => onChange(event.target.value)}
      placeholder="Type your answer"
      className="h-12 w-full rounded-xl border border-border bg-background px-4 outline-none transition focus:border-accent"
    />
  );
}
