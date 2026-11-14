import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Dumbbell,
  Lightbulb,
  Loader2,
  ThumbsDown,
  ThumbsUp,
  Wand2,
  X,
} from "lucide-react";
import { useState } from "react";

import { MarkdownContent } from "@/components/markdown-content";
import {
  answerCoachCheck,
  apiErrorMessage,
  explainConcept,
  getCoachPreferences,
  getFixIt,
  getPracticeSet,
  sendExplanationFeedback,
  type CoachCheck,
  type CoachCheckResult,
  type CoachExplanation,
  type ExplanationStyle,
  type FixIt,
  type SubmissionConcept,
} from "@/lib/api";

const STYLES: Array<{ id: ExplanationStyle; label: string }> = [
  { id: "simpler", label: "Simpler" },
  { id: "analogy", label: "Analogy" },
  { id: "example", label: "Worked example" },
  { id: "step_by_step", label: "Step by step" },
];

const BAND_LABELS: Record<string, string> = {
  weak: "Needs work",
  developing: "Developing",
  proficient: "Proficient",
  mastered: "Mastered",
};

function useRefreshLearnerData(sessionId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      [
        ["mastery"],
        ["weak-concepts"],
        ["next-recommendation"],
        ["due-reviews"],
        ["course", sessionId],
      ].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );
}

/** One multiple-choice check question. The answer stays on the server until
 * the learner commits to an option. */
export function CoachCheckQuestion({
  check,
  sessionId,
  onAnswered,
}: {
  check: CoachCheck;
  sessionId: string;
  onAnswered?: (result: CoachCheckResult) => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<CoachCheckResult | null>(
    check.result ?? null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = useRefreshLearnerData(sessionId);

  const submit = async () => {
    if (selected === null) return;
    setBusy(true);
    setError("");
    try {
      const outcome = await answerCoachCheck(check.check_id, selected);
      setResult(outcome);
      onAnswered?.(outcome);
      void refresh();
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not check this answer."));
    } finally {
      setBusy(false);
    }
  };

  const chosen = result ? result.selected_answer : selected;
  return (
    <div>
      <p className="font-medium leading-6">{check.question}</p>
      <div className="mt-3 grid gap-2">
        {check.options.map((option, index) => {
          const isCorrect = result?.correct_answer === index;
          const isChosen = chosen === index;
          const chosenWrong = Boolean(result) && isChosen && !isCorrect;
          return (
            <button
              key={`${index}-${option}`}
              type="button"
              disabled={Boolean(result) || busy}
              onClick={() => setSelected(index)}
              className={`flex items-start gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm transition ${
                result
                  ? isCorrect
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : chosenWrong
                      ? "border-destructive/40 bg-destructive/8"
                      : "border-border bg-background/40 opacity-70"
                  : isChosen
                    ? "border-accent bg-accent/10"
                    : "border-border bg-background/40 hover:bg-muted"
              }`}
            >
              <span className="mt-px shrink-0 font-semibold text-accent">
                {String.fromCharCode(65 + index)}
              </span>
              <span className="min-w-0 flex-1">{option}</span>
              {result && isCorrect && (
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-300" />
              )}
              {chosenWrong && (
                <X className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              )}
            </button>
          );
        })}
      </div>
      {!result && (
        <button
          type="button"
          onClick={() => void submit()}
          disabled={selected === null || busy}
          className="mt-3 inline-flex h-9 items-center gap-2 rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Check answer
        </button>
      )}
      {result && (
        <div
          className={`mt-3 rounded-xl px-3.5 py-3 text-sm leading-6 ${result.correct ? "bg-emerald-500/10" : "bg-destructive/8"}`}
        >
          <p className="font-semibold">
            {result.correct ? "Correct. Gap closed." : "Not quite."}
          </p>
          {!result.correct && result.misconception && (
            <p className="mt-1">
              <span className="font-medium">Likely confusion:</span>{" "}
              {result.misconception}
            </p>
          )}
          {result.explanation && (
            <p className="mt-1 text-muted-foreground">{result.explanation}</p>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </div>
  );
}

/** Explains why a wrong answer was tempting, gives the key idea, and asks one
 * fresh question on the same idea. */
export function FixItCard({
  submissionId,
  questionIndex,
  sessionId,
}: {
  submissionId: string;
  questionIndex: number;
  sessionId: string;
}) {
  const [fix, setFix] = useState<FixIt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setBusy(true);
    setError("");
    try {
      setFix(await getFixIt(submissionId, questionIndex));
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not prepare this fix."));
    } finally {
      setBusy(false);
    }
  };

  if (!fix) {
    return (
      <div className="mt-3">
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy}
          className="inline-flex h-9 items-center gap-2 rounded-full bg-accent/10 px-4 text-xs font-semibold text-accent transition hover:bg-accent/15 disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Wand2 className="h-3.5 w-3.5" />
          )}
          {busy ? "Preparing your fix" : "Fix this mistake"}
        </button>
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-accent/25 bg-accent/5 p-4">
      <div className="text-sm leading-6">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">
          Why your answer was tempting
        </p>
        <p className="mt-1">{fix.why_tempting}</p>
      </div>
      <div className="flex items-start gap-2.5 rounded-lg bg-background/70 p-3 text-sm leading-6">
        <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-300" />
        <p>
          <span className="font-semibold">Key idea:</span> {fix.key_idea}
        </p>
      </div>
      {fix.check && (
        <div className="border-t border-accent/15 pt-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Check you have it now
          </p>
          <CoachCheckQuestion check={fix.check} sessionId={sessionId} />
        </div>
      )}
    </div>
  );
}

/** Per-concept help after an assessment: a different explanation and a short
 * set of fresh practice questions. */
export function ConceptCoachPanel({
  sessionId,
  concepts,
  title = "Strengthen what you missed",
  description = "Get a different explanation or a few fresh questions on each concept. This is free and does not use your daily generations.",
}: {
  sessionId: string;
  concepts: SubmissionConcept[];
  title?: string;
  description?: string;
}) {
  const preferences = useQuery({
    queryKey: ["coach-preferences"],
    queryFn: getCoachPreferences,
    staleTime: 60_000,
  });
  if (!concepts.length) return null;
  return (
    <section className="rounded-2xl border border-border bg-card p-4 sm:p-5">
      <h3 className="font-display text-xl tracking-tight">{title}</h3>
      <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
      <div className="mt-4 space-y-3">
        {concepts.map((concept) => (
          <ConceptCoachRow
            key={concept.concept_id}
            sessionId={sessionId}
            concept={concept}
            preferredStyle={preferences.data?.explanation_style ?? null}
          />
        ))}
      </div>
    </section>
  );
}

function ConceptCoachRow({
  sessionId,
  concept,
  preferredStyle,
}: {
  sessionId: string;
  concept: SubmissionConcept;
  preferredStyle: ExplanationStyle | null;
}) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"explain" | "practice" | null>(null);
  const [style, setStyle] = useState<ExplanationStyle | null>(null);
  const [explanation, setExplanation] = useState<CoachExplanation | null>(null);
  const [checks, setChecks] = useState<CoachCheck[] | null>(null);
  const [practiceScore, setPracticeScore] = useState({ done: 0, correct: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const explain = async (next: ExplanationStyle) => {
    setMode("explain");
    setStyle(next);
    setBusy(true);
    setError("");
    try {
      setExplanation(await explainConcept(sessionId, concept.concept_id, next));
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not load this explanation."));
    } finally {
      setBusy(false);
    }
  };

  const practice = async () => {
    setMode("practice");
    setBusy(true);
    setError("");
    setChecks(null);
    setPracticeScore({ done: 0, correct: 0 });
    try {
      setChecks((await getPracticeSet(sessionId, concept.concept_id)).checks);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not create practice questions."));
    } finally {
      setBusy(false);
    }
  };

  const rate = async (helpful: boolean) => {
    if (!explanation) return;
    setExplanation({ ...explanation, helpful });
    try {
      await sendExplanationFeedback(explanation.explanation_id, helpful);
      if (helpful) {
        void queryClient.invalidateQueries({ queryKey: ["coach-preferences"] });
      }
    } catch {
      // Feedback is optional; the explanation stays usable if it fails.
    }
  };

  const orderedStyles = preferredStyle
    ? [
        ...STYLES.filter((item) => item.id === preferredStyle),
        ...STYLES.filter((item) => item.id !== preferredStyle),
      ]
    : STYLES;

  return (
    <article className="rounded-xl border border-border bg-background/45 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h4 className="font-semibold">{concept.concept_label}</h4>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {[
              concept.asked > 0
                ? `Missed ${concept.missed} of ${concept.asked}`
                : null,
              concept.band
                ? (BAND_LABELS[concept.band] ?? concept.band)
                : "Not practised yet",
              concept.current_mastery !== null
                ? `${Math.round(concept.current_mastery * 100)}% mastery`
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void explain(style ?? orderedStyles[0].id)}
            disabled={busy}
            className={`inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-xs font-semibold transition disabled:opacity-60 ${mode === "explain" ? "bg-accent text-accent-foreground" : "bg-accent/10 text-accent hover:bg-accent/15"}`}
          >
            <Lightbulb className="h-3.5 w-3.5" /> Explain differently
          </button>
          <button
            type="button"
            onClick={() => void practice()}
            disabled={busy}
            className={`inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-xs font-semibold transition disabled:opacity-60 ${mode === "practice" ? "bg-accent text-accent-foreground" : "bg-accent/10 text-accent hover:bg-accent/15"}`}
          >
            <Dumbbell className="h-3.5 w-3.5" />
            {checks ? "New practice set" : "Practise 3 questions"}
          </button>
        </div>
      </div>

      {mode === "explain" && (
        <div className="mt-4 border-t border-border pt-4">
          <div className="flex flex-wrap gap-1.5">
            {orderedStyles.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void explain(item.id)}
                disabled={busy}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${style === item.id ? "border-accent bg-accent/10 text-foreground" : "border-border text-muted-foreground hover:bg-muted"}`}
              >
                {item.label}
              </button>
            ))}
          </div>
          {busy && <CoachLoading label="Writing a new explanation" />}
          {!busy && explanation && (
            <div className="mt-3">
              <div className="text-sm leading-7">
                <MarkdownContent content={explanation.explanation} />
              </div>
              <p className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-sm">
                <span className="font-semibold">Takeaway:</span>{" "}
                {explanation.takeaway}
              </p>
              <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                <span>Did this help?</span>
                <button
                  type="button"
                  aria-label="This helped"
                  onClick={() => void rate(true)}
                  className={`grid h-7 w-7 place-items-center rounded-full transition hover:bg-muted ${explanation.helpful === true ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" : ""}`}
                >
                  <ThumbsUp className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  aria-label="This did not help"
                  onClick={() => void rate(false)}
                  className={`grid h-7 w-7 place-items-center rounded-full transition hover:bg-muted ${explanation.helpful === false ? "bg-destructive/10 text-destructive" : ""}`}
                >
                  <ThumbsDown className="h-3.5 w-3.5" />
                </button>
                {explanation.helpful === false && (
                  <span>Try another style above.</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {mode === "practice" && (
        <div className="mt-4 border-t border-border pt-4">
          {busy && <CoachLoading label="Writing fresh questions" />}
          {!busy && checks && (
            <div className="space-y-5">
              {checks.map((check, index) => (
                <div key={check.check_id}>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                    Question {index + 1} · {check.difficulty}
                  </p>
                  <CoachCheckQuestion
                    check={check}
                    sessionId={sessionId}
                    onAnswered={(result) =>
                      setPracticeScore((current) => ({
                        done: current.done + 1,
                        correct: current.correct + (result.correct ? 1 : 0),
                      }))
                    }
                  />
                </div>
              ))}
              {practiceScore.done === checks.length && (
                <p className="rounded-lg bg-muted/60 px-3 py-2 text-sm font-medium">
                  {practiceScore.correct} of {checks.length} correct.{" "}
                  {practiceScore.correct === checks.length
                    ? "You have this concept now."
                    : "Read a different explanation, then try a new set."}
                </p>
              )}
            </div>
          )}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
    </article>
  );
}

function CoachLoading({ label }: { label: string }) {
  return (
    <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}
