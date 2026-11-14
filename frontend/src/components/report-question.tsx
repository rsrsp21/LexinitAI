import { Flag, Loader2 } from "lucide-react";
import { useState } from "react";

import {
  apiErrorMessage,
  reportQuestion,
  type QuestionReportReason,
} from "@/lib/api";

const REASONS: Array<{ id: QuestionReportReason; label: string }> = [
  { id: "wrong_answer", label: "The marked answer is wrong" },
  { id: "unclear", label: "The question is unclear" },
  { id: "off_topic", label: "It is not about this course" },
  { id: "other", label: "Something else" },
];

/** Lets a learner flag a faulty question. A reported assessment question is
 * not asked again. */
export function ReportQuestion({
  source,
  referenceId,
  questionIndex,
}: {
  source: "assessment" | "final" | "check";
  referenceId: string;
  questionIndex: number;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<QuestionReportReason>("wrong_answer");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const send = async () => {
    setBusy(true);
    setError("");
    try {
      await reportQuestion({
        source,
        reference_id: referenceId,
        question_index: questionIndex,
        reason,
        note,
      });
      setSent(true);
      setOpen(false);
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not send this report."));
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <p className="mt-3 text-xs text-muted-foreground">
        Thanks. This question is flagged for review and will not be asked again.
      </p>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition hover:text-foreground"
      >
        <Flag className="h-3.5 w-3.5" /> Report this question
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-border bg-background/60 p-3">
      <p className="text-sm font-medium">What is wrong with this question?</p>
      <div className="mt-2 grid gap-1.5">
        {REASONS.map((item) => (
          <label key={item.id} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`report-${referenceId}-${questionIndex}`}
              checked={reason === item.id}
              onChange={() => setReason(item.id)}
            />
            {item.label}
          </label>
        ))}
      </div>
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        maxLength={500}
        rows={2}
        placeholder="Add a detail (optional)"
        className="mt-2 w-full resize-none rounded-lg border border-border bg-background p-2 text-sm outline-none transition focus:border-accent"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void send()}
          disabled={busy}
          className="inline-flex h-8 items-center gap-2 rounded-full bg-primary px-3.5 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Send report
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="h-8 rounded-full px-3 text-xs font-semibold text-muted-foreground transition hover:bg-muted"
        >
          Cancel
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </div>
  );
}
