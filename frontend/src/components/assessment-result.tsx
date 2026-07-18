import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Loader2,
  RotateCcw,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { useState } from "react";

import {
  apiErrorMessage,
  getAssessmentSubmission,
  type AssessmentSubmissionQuestion,
} from "@/lib/api";

export function AssessmentResult({
  submissionId,
  sessionId,
  moduleId,
}: {
  submissionId: string;
  sessionId: string;
  moduleId?: string;
}) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ["assessment-submission", submissionId],
    queryFn: () => getAssessmentSubmission(submissionId),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading your result
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-2xl border border-destructive/25 bg-destructive/8 p-5 text-sm text-destructive">
        {apiErrorMessage(error, "Could not load this assessment result.")}
      </div>
    );
  }

  const effectiveModule = moduleId || data.module_id || undefined;
  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-2xl border border-accent/30 bg-accent/10 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className={`grid h-12 w-12 place-items-center rounded-full ${data.percentage >= 50 ? "bg-accent text-accent-foreground" : "bg-destructive text-destructive-foreground"}`}>
              {data.percentage >= 50 ? <CheckCircle2 className="h-6 w-6" /> : <X className="h-6 w-6" />}
            </span>
            <div>
              <p className="text-sm font-medium text-muted-foreground">
                {data.percentage >= 50 ? "Passed!" : "Score too low to mark completed"}
              </p>
              <h3 className="font-display text-3xl tracking-tight">
                {data.score} / {data.total}
              </h3>
            </div>
          </div>
          <span className={`font-display text-4xl tracking-tight ${data.percentage >= 50 ? "text-accent" : "text-destructive"}`}>
            {Math.round(data.percentage)}%
          </span>
        </div>
      </section>

      {data.weak_topic && (
        <section className="rounded-2xl border border-amber-500/25 bg-amber-500/10 p-5">
          <div className="flex items-start gap-3">
            <Target className="mt-0.5 h-5 w-5 shrink-0 text-amber-700 dark:text-amber-300" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Focus topic
              </p>
              <h3 className="mt-1 font-display text-xl tracking-tight">
                {data.weak_topic}
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Build a focused course to strengthen this topic with fresh
                explanations and practice.
              </p>
            </div>
          </div>
          <Link
            to="/app/new-course"
            search={{
              topic: data.weak_topic,
              assessment_submission_id: data.submission_id,
              adaptive_from_session: data.session_id,
              adaptive_from_topic: data.source_topic,
            }}
            className="mt-4 inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
          >
            <Sparkles className="h-4 w-4" /> Generate from weak topic
          </Link>
        </section>
      )}

      <Link
        to="/app/session/$id/assessments"
        params={{ id: sessionId }}
        search={{
          module: effectiveModule,
          submission: undefined,
          type: data.assessment_type,
          reattempt: data.submission_id,
        }}
        className="inline-flex h-11 items-center gap-2 rounded-full border border-border bg-background px-5 text-sm font-semibold transition hover:bg-muted"
      >
        <RotateCcw className="h-4 w-4" /> Reattempt assessment
        <ArrowRight className="h-4 w-4" />
      </Link>

      <section className="overflow-hidden rounded-2xl border border-border bg-card">
        <button
          type="button"
          onClick={() => setReviewOpen((current) => !current)}
          aria-expanded={reviewOpen}
          className="flex w-full items-center justify-between gap-4 p-4 text-left transition hover:bg-muted/60 sm:p-5"
        >
          <span>
            <span className="block font-display text-xl tracking-tight">
              Review answers
            </span>
            <span className="mt-0.5 block text-sm text-muted-foreground">
              {data.questions.length} question
              {data.questions.length === 1 ? "" : "s"} · correct and selected
              answers
            </span>
          </span>
          <ChevronDown
            className={`h-5 w-5 shrink-0 text-muted-foreground transition-transform ${reviewOpen ? "rotate-180" : ""}`}
          />
        </button>
        {reviewOpen && (
          <div className="space-y-3 border-t border-border p-4 sm:p-5">
            {data.questions.map((question, index) => (
              <QuestionResult
                key={`${data.submission_id}-${index}`}
                question={question}
                index={index}
                assessmentType={data.assessment_type}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function QuestionResult({
  question,
  index,
  assessmentType,
}: {
  question: AssessmentSubmissionQuestion;
  index: number;
  assessmentType: "mcq" | "truefalse" | "oneword";
}) {
  return (
    <article className="rounded-2xl border border-border bg-background/45 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full ${question.correct ? "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300" : "bg-destructive/10 text-destructive"}`}
        >
          {question.correct ? (
            <Check className="h-4 w-4" />
          ) : (
            <X className="h-4 w-4" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="font-semibold">
            {index + 1}. {question.question}
          </h4>
          {assessmentType === "oneword" ? (
            <OneWordReview question={question} />
          ) : (
            <ChoiceReview question={question} assessmentType={assessmentType} />
          )}
          {question.explanation && (
            <p className="mt-3 border-t border-border pt-3 text-sm leading-6 text-muted-foreground">
              {question.explanation}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

function ChoiceReview({
  question,
  assessmentType,
}: {
  question: AssessmentSubmissionQuestion;
  assessmentType: "mcq" | "truefalse";
}) {
  const options =
    assessmentType === "truefalse" ? ["True", "False"] : question.options;
  const selectedIndex = choiceIndex(
    question.selected_answer,
    options,
    assessmentType,
  );
  const correctIndex = choiceIndex(
    question.correct_answer,
    options,
    assessmentType,
  );
  return (
    <div className="mt-4 grid gap-2">
      {options.map((option, optionIndex) => {
        const correct = optionIndex === correctIndex;
        const selected = optionIndex === selectedIndex;
        const selectedWrong = selected && !correct;
        return (
          <div
            key={`${optionIndex}-${option}`}
            className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${correct ? "border-emerald-500/35 bg-emerald-500/10" : selectedWrong ? "border-destructive/35 bg-destructive/8" : "border-border bg-background/45"}`}
          >
            <span
              className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${correct ? "bg-emerald-500 text-white" : selectedWrong ? "bg-destructive text-destructive-foreground" : "border border-border text-muted-foreground"}`}
            >
              {correct ? (
                <Check className="h-4 w-4" />
              ) : selectedWrong ? (
                <X className="h-4 w-4" />
              ) : assessmentType === "mcq" ? (
                String.fromCharCode(65 + optionIndex)
              ) : (
                <span className="h-2 w-2 rounded-full bg-current opacity-45" />
              )}
            </span>
            <span className="min-w-0 flex-1 font-medium">{option}</span>
            <span className="flex flex-wrap justify-end gap-1.5 text-xs font-semibold">
              {selected && (
                <span
                  className={
                    selectedWrong
                      ? "text-destructive"
                      : "text-emerald-700 dark:text-emerald-300"
                  }
                >
                  Your answer
                </span>
              )}
              {correct && !selected && (
                <span className="text-emerald-700 dark:text-emerald-300">
                  Correct answer
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function OneWordReview({
  question,
}: {
  question: AssessmentSubmissionQuestion;
}) {
  return (
    <div className="mt-4 grid gap-2 text-sm">
      <AnswerRow
        correct={question.correct}
        label="Your answer"
        value={answerLabel(question, false)}
      />
      {!question.correct && (
        <AnswerRow
          correct
          label="Correct answer"
          value={answerLabel(question, true)}
        />
      )}
    </div>
  );
}

function AnswerRow({
  correct,
  label,
  value,
}: {
  correct: boolean;
  label: string;
  value: string;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${correct ? "border-emerald-500/35 bg-emerald-500/10" : "border-destructive/35 bg-destructive/8"}`}
    >
      <span
        className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-white ${correct ? "bg-emerald-500" : "bg-destructive"}`}
      >
        {correct ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
      </span>
      <span className="text-muted-foreground">{label}</span>
      <strong className="ml-auto text-right">{value}</strong>
    </div>
  );
}

function choiceIndex(
  value: number | boolean | string | null,
  options: string[],
  assessmentType: "mcq" | "truefalse",
) {
  if (assessmentType === "truefalse") {
    if (value === true || String(value).toLowerCase() === "true") return 0;
    if (value === false || String(value).toLowerCase() === "false") return 1;
    return -1;
  }
  if (typeof value === "number") return value;
  return options.findIndex(
    (option) =>
      option.trim().toLowerCase() === String(value).trim().toLowerCase(),
  );
}

function answerLabel(question: AssessmentSubmissionQuestion, correct: boolean) {
  const value = correct ? question.correct_answer : question.selected_answer;
  if (!correct && question.selected_option) return question.selected_option;
  if (typeof value === "number" && question.options[value])
    return question.options[value];
  if (typeof value === "boolean") return value ? "True" : "False";
  if (value === null || value === "") return "No answer";
  return String(value);
}
