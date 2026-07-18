import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";

import {
  apiErrorMessage,
  deleteLearningSource,
  getSourcePage,
  getSources,
  retryLearningSource,
  type LearningSource,
} from "@/lib/api";

export function SourcePicker({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (sourceIds: string[]) => void;
}) {
  const queryClient = useQueryClient();
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: getSources,
    staleTime: 15_000,
  });
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{
    sourceId: string;
    filename: string;
    page: number;
    pageCount: number;
    text: string;
  } | null>(null);

  const toggle = (source: LearningSource) => {
    if (source.status !== "ready") return;
    if (selected.includes(source.source_id)) {
      onChange(selected.filter((item) => item !== source.source_id));
      return;
    }
    if (selected.length >= 5) {
      setError("Choose up to five sources.");
      return;
    }
    setError("");
    onChange([...selected, source.source_id]);
  };

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["sources"] });
  };

  const retry = async (sourceId: string) => {
    setBusyId(sourceId);
    setError("");
    try {
      await retryLearningSource(sourceId);
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not retry this source."));
    } finally {
      setBusyId("");
    }
  };

  const remove = async (source: LearningSource) => {
    if (
      !window.confirm(`Remove “${source.filename}” from your source library?`)
    )
      return;
    setBusyId(source.source_id);
    setError("");
    try {
      await deleteLearningSource(source.source_id);
      onChange(selected.filter((item) => item !== source.source_id));
      if (preview?.sourceId === source.source_id) setPreview(null);
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not remove this source."));
    } finally {
      setBusyId("");
    }
  };

  const showPage = async (source: LearningSource, page = 1) => {
    setBusyId(source.source_id);
    setError("");
    try {
      const result = await getSourcePage(source.source_id, page);
      setPreview({
        sourceId: source.source_id,
        filename: result.filename,
        page: result.page_number,
        pageCount: result.page_count,
        text: result.text,
      });
    } catch (err) {
      setError(apiErrorMessage(err, "Could not open this source."));
    } finally {
      setBusyId("");
    }
  };

  const items = sources.data?.sources ?? [];
  if (!sources.isLoading && items.length === 0) return null;

  return (
    <section className="mx-auto max-w-3xl rounded-[22px] border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-foreground">
            Your sources
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Choose up to five sources to create a source-grounded course.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          aria-label="Refresh sources"
          className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <RefreshCw
            className={`h-4 w-4 ${sources.isFetching ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      {sources.isLoading ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading sources…
        </div>
      ) : (
        <div className="app-scrollbar mt-4 max-h-56 space-y-2 overflow-y-auto pr-1">
          {items.map((source) => {
            const active = selected.includes(source.source_id);
            const busy = busyId === source.source_id;
            return (
              <div
                key={source.source_id}
                className={`flex items-center gap-3 rounded-2xl border p-3 transition ${
                  active
                    ? "border-accent/45 bg-accent/10"
                    : "border-border bg-background/55"
                }`}
              >
                <button
                  type="button"
                  disabled={source.status !== "ready" || busy}
                  onClick={() => toggle(source)}
                  aria-label={`${active ? "Deselect" : "Select"} ${source.filename}`}
                  className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
                    active
                      ? "bg-accent text-accent-foreground"
                      : "bg-muted text-muted-foreground"
                  } disabled:opacity-60`}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : active ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <FileText className="h-4 w-4" />
                  )}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-foreground">
                    {source.filename}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {source.status === "ready"
                      ? `${source.page_count} ${source.page_count === 1 ? "page" : "pages"} · ${formatBytes(source.size_bytes)}`
                      : source.status === "failed"
                        ? source.error_message ||
                          "This source could not be read."
                        : "Preparing source…"}
                  </div>
                </div>
                {source.status === "ready" && (
                  <button
                    type="button"
                    onClick={() => void showPage(source)}
                    className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    aria-label={`Preview ${source.filename}`}
                  >
                    <Search className="h-4 w-4" />
                  </button>
                )}
                {source.status === "failed" && (
                  <button
                    type="button"
                    onClick={() => void retry(source.source_id)}
                    className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    aria-label={`Retry ${source.filename}`}
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void remove(source)}
                  className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
                  aria-label={`Remove ${source.filename}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {preview && (
        <div className="mt-4 rounded-2xl border border-border bg-background/70 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 text-sm font-semibold text-foreground">
              <span className="truncate">{preview.filename}</span>
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                Page {preview.page} of {preview.pageCount}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setPreview(null)}
              aria-label="Close source preview"
              className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground hover:bg-muted"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="app-scrollbar mt-3 max-h-52 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
            {preview.text}
          </div>
          {preview.pageCount > 1 && (
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={preview.page <= 1}
                onClick={() => {
                  const source = items.find(
                    (item) => item.source_id === preview.sourceId,
                  );
                  if (source) void showPage(source, preview.page - 1);
                }}
                className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-40"
              >
                Previous page
              </button>
              <button
                type="button"
                disabled={preview.page >= preview.pageCount}
                onClick={() => {
                  const source = items.find(
                    (item) => item.source_id === preview.sourceId,
                  );
                  if (source) void showPage(source, preview.page + 1);
                }}
                className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-40"
              >
                Next page
              </button>
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
    </section>
  );
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
