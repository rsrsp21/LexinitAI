import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  Loader2,
  PlayCircle,
  RefreshCw,
  Sparkles,
  Subtitles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { YouTubeLearningPlayer } from "@/components/youtube-learning-player";
import { SessionBackButton } from "@/components/session-back-button";
import { useSession } from "@/hooks/use-session";
import { sessionTitle } from "@/lib/session-utils";
import {
  apiErrorMessage,
  createIdempotencyKey,
  getVideoCatalog,
  getVideoStudyGuide,
  saveVideoProgress,
  submitVideoRetrievalCheck,
  type VideoCatalogItem,
  type VideoPlaybackState,
  type VideoRetrievalResult,
} from "@/lib/api";
import { preloadCoursePage } from "@/lib/route-prefetch";

export const Route = createFileRoute("/app/session/$id/videos")({
  beforeLoad: ({ context, params }) =>
    preloadCoursePage(context.queryClient, params.id, { videos: true }),
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
  }),
  head: () => ({ meta: [{ title: "Video Lectures - Lexinit" }] }),
  component: Videos,
});

function Videos() {
  const { id } = Route.useParams();
  const { module } = Route.useSearch();
  const { data: sessionData } = useSession(id);
  const session = sessionData?.session;
  const queryClient = useQueryClient();
  const catalog = useQuery({
    queryKey: ["video-catalog", id],
    queryFn: () => getVideoCatalog(id),
    staleTime: 5 * 60 * 1000,
  });
  const metadataHydrationRef = useRef("");
  const [selectedId, setSelectedId] = useState("");
  const [autoplayVideoId, setAutoplayVideoId] = useState("");
  const videos = useMemo(() => {
    const all = catalog.data?.videos ?? [];
    return module ? all.filter((video) => video.module_id === module) : all;
  }, [catalog.data?.videos, module]);
  const selected =
    videos.find((video) => video.video_id === selectedId) ?? videos[0];

  useEffect(() => {
    if (!catalog.data || metadataHydrationRef.current === id) return;
    metadataHydrationRef.current = id;
    let active = true;
    void getVideoCatalog(id, false, true)
      .then((result) => {
        if (active) queryClient.setQueryData(["video-catalog", id], result);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [catalog.data, id, queryClient]);

  useEffect(() => {
    if (!selectedId && videos[0]) setSelectedId(videos[0].video_id);
    if (
      selectedId &&
      videos.length &&
      !videos.some((item) => item.video_id === selectedId)
    ) {
      setSelectedId(videos[0].video_id);
    }
  }, [selectedId, videos]);

  const guide = useQuery({
    queryKey: ["video-study-guide", id, selected?.video_id],
    queryFn: () => getVideoStudyGuide(id, selected!.video_id),
    enabled: false,
    retry: false,
  });
  const shorterAlternative = useMemo(
    () =>
      selected
        ? videos
            .filter(
              (video) =>
                video.video_id !== selected.video_id &&
                video.module_id === selected.module_id &&
                video.duration_seconds > 0 &&
                video.duration_seconds < selected.duration_seconds * 0.8,
            )
            .sort(
              (left, right) => left.duration_seconds - right.duration_seconds,
            )[0]
        : undefined,
    [selected, videos],
  );
  const [answers, setAnswers] = useState<string[]>([]);
  const [submission, setSubmission] = useState<VideoRetrievalResult | null>(
    null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const guideQuestions = guide.data?.questions;

  useEffect(() => {
    setAnswers(guideQuestions?.map(() => "") ?? []);
    setSubmission(null);
    setSubmitError("");
  }, [guide.data?.guide_id, guideQuestions]);

  const persistProgress = useCallback(
    async (
      positionSeconds: number,
      durationSeconds: number,
      state: VideoPlaybackState,
    ) => {
      if (!selected) return;
      const result = await saveVideoProgress(id, selected.video_id, {
        position_seconds: positionSeconds,
        duration_seconds: durationSeconds,
        state,
      });
      queryClient.setQueryData(
        ["video-catalog", id],
        (
          current:
            | {
                session_id: string;
                videos: VideoCatalogItem[];
                count: number;
              }
            | undefined,
        ) =>
          current
            ? {
                ...current,
                videos: current.videos.map((video) =>
                  video.video_id === selected.video_id
                    ? {
                        ...video,
                        position_seconds: result.position_seconds,
                        furthest_position_seconds:
                          result.furthest_position_seconds,
                        progress_percent: result.progress_percent,
                        completed: result.completed,
                      }
                    : video,
                ),
              }
            : current,
      );
      if (result.completed) {
        await queryClient.invalidateQueries({ queryKey: ["course", id] });
        await queryClient.invalidateQueries({ queryKey: ["courses"] });
      }
    },
    [id, queryClient, selected],
  );

  const playNextVideo = useCallback(() => {
    if (!selected) return;
    const currentIndex = videos.findIndex(
      (video) => video.video_id === selected.video_id,
    );
    const nextVideo = videos[currentIndex + 1];
    if (!nextVideo) return;
    setAutoplayVideoId(nextVideo.video_id);
    setSelectedId(nextVideo.video_id);
  }, [selected, videos]);

  const selectVideo = (videoId: string) => {
    setAutoplayVideoId("");
    setSelectedId(videoId);
  };

  const submitCheck = async () => {
    if (!selected || !guide.data || answers.some((answer) => !answer.trim())) {
      setSubmitError("Answer every retrieval question before submitting.");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    const keyStorage = `lexinit:video-check:${guide.data.guide_id}`;
    let idempotencyKey = window.localStorage.getItem(keyStorage);
    if (!idempotencyKey) {
      idempotencyKey = createIdempotencyKey("video-retrieval");
      window.localStorage.setItem(keyStorage, idempotencyKey);
    }
    try {
      const result = await submitVideoRetrievalCheck(
        id,
        selected.video_id,
        guide.data.guide_id,
        answers,
        idempotencyKey,
      );
      window.localStorage.removeItem(keyStorage);
      setSubmission(result);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["mastery"] }),
        queryClient.invalidateQueries({ queryKey: ["weak-concepts"] }),
        queryClient.invalidateQueries({ queryKey: ["next-recommendation"] }),
        queryClient.invalidateQueries({ queryKey: ["course", id] }),
        queryClient.invalidateQueries({ queryKey: ["courses"] }),
      ]);
    } catch (cause) {
      setSubmitError(
        apiErrorMessage(cause, "Could not submit this video knowledge check."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="flex min-w-0 items-center gap-3">
          <SessionBackButton sessionId={id} />
          <PlayCircle className="h-8 w-8 shrink-0 text-accent" />
          <h1 className="min-w-0 font-display text-3xl leading-[1.05] tracking-tight sm:text-4xl">
            {catalog.isLoading ? "Loading Video Lectures" : "Video Lectures"}
          </h1>
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-sm text-muted-foreground">
          <span className="rounded-full border border-border bg-background/40 px-3 py-1.5">
            <span className="font-medium text-foreground">Topic:</span>{" "}
            {sessionTitle(session)}
          </span>
          <span className="rounded-full border border-accent/25 bg-accent/10 px-3 py-1.5 text-accent">
            <span className="font-medium">Module:</span>{" "}
            {selected?.module_title || "All modules"}
          </span>
        </div>
      </header>

      {catalog.isLoading && <LoadingPanel label="Loading lecture catalog…" />}
      {catalog.isError && (
        <ErrorPanel
          message={apiErrorMessage(
            catalog.error,
            "Could not load the video lectures.",
          )}
          onRetry={() => void catalog.refetch()}
        />
      )}
      {!catalog.isLoading && !catalog.isError && videos.length === 0 && (
        <div className="rounded-2xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
          No video lectures are available in this course yet.
        </div>
      )}

      {selected && (
        <div>
          <main className="space-y-6">
            <section className="rounded-2xl border border-border bg-card p-4 shadow-sm sm:p-6">
              <YouTubeLearningPlayer
                key={selected.video_id}
                videoId={selected.video_id}
                resumeAt={selected.position_seconds}
                autoplay={autoplayVideoId === selected.video_id}
                onProgress={persistProgress}
                onEnded={playNextVideo}
              />
              <div className="mt-5 flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
                    {selected.module_title}
                  </div>
                  <h2 className="mt-1 font-display text-3xl leading-tight tracking-tight">
                    {selected.title}
                  </h2>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span>{selected.channel}</span>
                    <span className="inline-flex items-center gap-1">
                      <Clock3 className="h-3.5 w-3.5" />
                      {formatDuration(selected.duration_seconds)}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Subtitles className="h-3.5 w-3.5" />
                      {transcriptLabel(selected.transcript_status)}
                    </span>
                  </div>
                </div>
                <a
                  href={selected.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-10 items-center gap-2 rounded-full border border-border bg-background px-4 text-sm font-semibold transition hover:bg-muted"
                >
                  YouTube <ExternalLink className="h-4 w-4" />
                </a>
              </div>
              <div className="mt-5 rounded-xl border border-accent/20 bg-accent/10 p-4 text-sm leading-6">
                <div className="flex items-start gap-2">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <span>{selected.recommendation_reason}</span>
                </div>
                {selected.coverage_labels.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="self-center text-xs font-semibold text-foreground">
                      Covers
                    </span>
                    {selected.coverage_labels.map((concept) => (
                      <span
                        key={concept}
                        className="rounded-full border border-accent/20 bg-background/55 px-3 py-1 text-xs text-muted-foreground"
                      >
                        {concept}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="mt-4">
                <div className="mb-2 flex justify-between text-xs text-muted-foreground">
                  <span>
                    {selected.completed ? "Completed" : "Playback progress"}
                  </span>
                  <span>{selected.progress_percent}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-accent transition-[width]"
                    style={{ width: `${selected.progress_percent}%` }}
                  />
                </div>
              </div>
              {selected.position_seconds > 0 &&
                selected.progress_percent < 30 &&
                shorterAlternative && (
                  <button
                    type="button"
                    onClick={() => selectVideo(shorterAlternative.video_id)}
                    className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-accent hover:underline"
                  >
                    Try a shorter{" "}
                    {formatDuration(shorterAlternative.duration_seconds)}
                    alternative
                  </button>
                )}
            </section>

            <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 font-semibold">
                    <FileText className="h-4 w-4 text-accent" /> Lecture Guide
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Grounded summary, timestamped moments, and retrieval
                    questions.
                  </p>
                </div>
                {!guide.data && (
                  <button
                    type="button"
                    onClick={() => void guide.refetch()}
                    disabled={guide.isFetching}
                    className="inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
                  >
                    {guide.isFetching ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <BookOpenCheck className="h-4 w-4" />
                    )}
                    {selected.summary_status === "ready"
                      ? "Open Lecture Guide"
                      : "Build Lecture Guide"}
                  </button>
                )}
              </div>
              {guide.isError && (
                <p className="mt-4 rounded-xl bg-destructive/5 p-4 text-sm text-destructive">
                  {apiErrorMessage(
                    guide.error,
                    "Could not build the Lecture Guide.",
                  )}
                </p>
              )}
              {guide.data?.status === "unavailable" && (
                <div className="mt-4 rounded-xl border border-border bg-background/50 p-4 text-sm text-muted-foreground">
                  <p>
                    {guide.data.retryable
                      ? "The captions could not be reached just now. Please try again."
                      : "Captions are not available for this lecture. You can still watch it, but a reliable summary cannot be created without them."}
                  </p>
                  {guide.data.retryable && (
                    <button
                      type="button"
                      onClick={() => void guide.refetch()}
                      disabled={guide.isFetching}
                      className="mt-3 inline-flex h-9 items-center gap-2 rounded-full border border-border bg-card px-4 text-sm font-semibold disabled:opacity-50"
                    >
                      {guide.isFetching ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                      Try again
                    </button>
                  )}
                </div>
              )}
              {guide.data?.status === "ready" && (
                <div className="mt-6 space-y-6">
                  <div>
                    <h3 className="font-display text-2xl tracking-tight">
                      Key ideas
                    </h3>
                    <ul className="mt-3 grid gap-2 text-sm leading-6 text-muted-foreground">
                      {guide.data.summary_points.map((point) => (
                        <li
                          key={point}
                          className="rounded-xl bg-background/55 px-4 py-3"
                        >
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {guide.data.key_moments.length > 0 && (
                    <div>
                      <h3 className="font-display text-2xl tracking-tight">
                        Key moments
                      </h3>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {guide.data.key_moments.map((moment) => (
                          <div
                            key={`${moment.start_seconds}-${moment.note}`}
                            className="rounded-xl border border-border bg-background/45 p-4 text-sm"
                          >
                            <span className="font-semibold text-accent">
                              {formatClock(moment.start_seconds)}
                            </span>
                            <p className="mt-1 leading-6 text-muted-foreground">
                              {moment.note}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="border-t border-border pt-6">
                    <h3 className="font-display text-2xl tracking-tight">
                      Quick check
                    </h3>
                    {!selected.completed && (
                      <p className="mt-2 rounded-xl bg-muted/60 p-4 text-sm text-muted-foreground">
                        Finish the lecture to unlock submission. The questions
                        are visible now so you know what ideas to listen for.
                      </p>
                    )}
                    <div className="mt-4 grid gap-4">
                      {guide.data.questions.map((question, index) => (
                        <label
                          key={question.question_id}
                          className="grid gap-2 text-sm"
                        >
                          <span className="font-semibold">
                            {index + 1}. {question.question}
                          </span>
                          <textarea
                            value={answers[index] ?? ""}
                            onChange={(event) =>
                              setAnswers((current) =>
                                current.map((answer, answerIndex) =>
                                  answerIndex === index
                                    ? event.target.value
                                    : answer,
                                ),
                              )
                            }
                            disabled={Boolean(submission)}
                            rows={3}
                            className="resize-none rounded-xl border border-border bg-background p-3 outline-none transition focus:border-accent disabled:opacity-70"
                          />
                        </label>
                      ))}
                    </div>
                    {!submission && (
                      <button
                        type="button"
                        onClick={() => void submitCheck()}
                        disabled={
                          !selected.completed ||
                          submitting ||
                          answers.some((answer) => !answer.trim())
                        }
                        className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
                      >
                        {submitting && (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        )}
                        Submit knowledge check
                      </button>
                    )}
                    {submitError && (
                      <p className="mt-3 text-sm text-destructive">
                        {submitError}
                      </p>
                    )}
                    {submission && (
                      <RetrievalFeedback submission={submission} />
                    )}
                  </div>
                </div>
              )}
            </section>
          </main>
        </div>
      )}
    </div>
  );
}

function RetrievalFeedback({
  submission,
}: {
  submission: VideoRetrievalResult;
}) {
  return (
    <div className="mt-5 space-y-3 rounded-2xl border border-accent/25 bg-accent/10 p-5">
      <div className="flex items-center gap-2 font-semibold">
        <CheckCircle2 className="h-5 w-5 text-accent" /> Knowledge check
        complete: {submission.score}/{submission.total}
      </div>
      {submission.feedback.map((item, index) => (
        <div
          key={`${submission.event_id}-${index}`}
          className="rounded-xl bg-background/55 p-4 text-sm"
        >
          <div className="font-semibold">
            Question {index + 1}: {item.correct ? "Correct" : "Review"}
          </div>
          {!item.correct && (
            <p className="mt-1 text-foreground">
              Expected: {item.expected_answer}
            </p>
          )}
          <p className="mt-1 leading-6 text-muted-foreground">
            {item.explanation}
          </p>
        </div>
      ))}
      <p className="text-xs leading-5 text-muted-foreground">
        Your learning profile and next recommendation are updated from these
        answers. Playback time alone does not change your progress.
      </p>
    </div>
  );
}

function LoadingPanel({ label }: { label: string }) {
  return (
    <div className="grid min-h-72 place-items-center rounded-2xl border border-border bg-card">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin text-accent" /> {label}
      </div>
    </div>
  );
}

function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-2xl border border-destructive/25 bg-destructive/5 p-6">
      <p className="text-sm text-destructive">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold"
      >
        <RefreshCw className="h-4 w-4" /> Retry
      </button>
    </div>
  );
}

function formatDuration(seconds: number) {
  if (!seconds) return "Duration unavailable";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function formatClock(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function transcriptLabel(status: VideoCatalogItem["transcript_status"]) {
  if (status === "available") return "Transcript available";
  if (status === "unknown") return "Transcript checking";
  return "No transcript";
}
