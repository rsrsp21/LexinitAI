import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { useState } from "react";

import { apiErrorMessage, deleteSession } from "@/lib/api";

const CONFIRM_WORD = "delete";

/** Permanently deletes a course with all of its attempts, results, progress,
 * mastery and badge. Asks the learner to type a word first. */
export function DeleteCourse({
  sessionId,
  topic,
}: {
  sessionId: string;
  topic: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await deleteSession(sessionId, sessionId.slice(-6));
      // Everything derived from the course is now stale.
      queryClient.removeQueries({ queryKey: ["course", sessionId] });
      queryClient.removeQueries({ queryKey: ["session", sessionId] });
      await queryClient.invalidateQueries();
      await navigate({ to: "/app" });
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not delete this course."));
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <div className="mt-6 flex justify-end">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete course
        </button>
      </div>
    );
  }

  return (
    <section className="mt-6 rounded-2xl border border-destructive/30 bg-destructive/5 p-5">
      <h3 className="font-semibold text-destructive">
        Delete “{topic}” permanently?
      </h3>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">
        This removes the course and everything in it: study materials,
        assessment attempts and results, final assessment, practice history,
        progress, mastery for its concepts, and its badge. This cannot be
        undone.
      </p>
      <label
        htmlFor="delete-course-confirm"
        className="mt-3 block text-sm font-medium"
      >
        Type <span className="font-semibold">{CONFIRM_WORD}</span> to confirm
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          id="delete-course-confirm"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoComplete="off"
          className="h-10 w-44 rounded-full border border-border bg-background px-4 text-sm outline-none transition focus:border-destructive"
        />
        <button
          type="button"
          onClick={() => void remove()}
          disabled={typed.trim().toLowerCase() !== CONFIRM_WORD || busy}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-destructive px-4 text-sm font-semibold text-destructive-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          Delete course
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setTyped("");
            setError("");
          }}
          disabled={busy}
          className="h-10 rounded-full px-4 text-sm font-semibold text-muted-foreground transition hover:bg-muted"
        >
          Cancel
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
    </section>
  );
}
