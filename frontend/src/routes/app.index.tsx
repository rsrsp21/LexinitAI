import {
  createFileRoute,
  Link,
  redirect,
  useNavigate,
} from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  Camera,
  Check,
  FileUp,
  Loader2,
  Mic,
  Plus,
  Sparkles,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type FormEvent,
} from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCurrentUser } from "@/hooks/use-current-user";
import { LearnerInsights } from "@/components/learner-insights";
import { CourseDashboard } from "@/components/course-dashboard";
import { GenerationProgressCard } from "@/components/generation-progress-card";
import { SourcePicker } from "@/components/source-picker";
import { useGenerationRun } from "@/hooks/use-generation-run";
import {
  apiErrorMessage,
  createIdempotencyKey,
  getCourses,
  requestJson,
  uploadLearningSource,
  type SubmitTopicResult,
} from "@/lib/api";

export const Route = createFileRoute("/app/")({
  beforeLoad: async ({ context }) => {
    const result = await context.queryClient
      .ensureQueryData({
        queryKey: ["courses"],
        queryFn: getCourses,
        staleTime: 15_000,
      })
      .catch(() => undefined);

    if (result && result.courses.length === 0) {
      throw redirect({ to: "/app/new-course" });
    }
  },
  head: () => ({
    meta: [
      { title: "My learning - Lexinit" },
      {
        name: "description",
        content: "Continue your courses or begin a new learning journey.",
      },
    ],
  }),
  component: DashboardHome,
});

export type NewCourseSearch = {
  topic?: string;
  assessment_submission_id?: string;
  adaptive_from_session?: string;
  adaptive_from_topic?: string;
};

type Mode = "quick" | "deep";
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionEventLike = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
};

// const SUGGESTED_TOPICS = [
//   "Bayesian statistics",
//   "React concurrent rendering",
//   "Antitrust in the platform era",
//   "Vector databases 101",
//   "Molecular orbital theory",
//   "Behavioral economics primer",
// ];

const GREETING_TEMPLATES = [
  { before: "Welcome back, ", after: "!" },
  { before: "Hi, ", after: "!" },
  { before: "Hello, ", after: "!" },
  { before: "Ready, ", after: "?" },
  { before: "Let's learn, ", after: "!" },
];

const NEW_COURSE_GREETING_TEMPLATES = [
  { before: "What's next, ", after: "?" },
  { before: "New course, ", after: "!" },
  { before: "Ready, ", after: "?" },
  { before: "New topic, ", after: "?" },
];

function DashboardHome() {
  const { data } = useCurrentUser();
  const firstName = data?.user?.name?.split(" ")?.[0] || "Learner";
  const greeting = useMemo(
    () =>
      GREETING_TEMPLATES[Math.floor(Math.random() * GREETING_TEMPLATES.length)],
    [],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-7 pt-2 lg:pt-3">
      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between"
      >
        <div>
          <h1 className="flex items-center gap-3 font-display text-4xl tracking-tight text-foreground sm:text-5xl">
            <Sparkles className="h-8 w-8 shrink-0 text-accent sm:h-9 sm:w-9" />
            {greeting.before}
            <strong className="font-semibold">{firstName}</strong>
            {greeting.after}
          </h1>
          <p className="mt-3 text-base text-muted-foreground">
            Continue where you left off or review what needs attention next.
          </p>
        </div>
        <Link
          to="/app/new-course"
          className="inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-full bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-sm transition hover:-translate-y-0.5 hover:opacity-90"
        >
          <Plus className="h-4 w-4" /> New course
        </Link>
      </motion.header>

      <CourseDashboard />
      <LearnerInsights />
    </div>
  );
}

export function NewCoursePage({ search }: { search: NewCourseSearch }) {
  const { data } = useCurrentUser();
  const firstName = data?.user?.name?.split(" ")?.[0] || "Learner";
  const greeting = useMemo(
    () =>
      NEW_COURSE_GREETING_TEMPLATES[
        Math.floor(Math.random() * NEW_COURSE_GREETING_TEMPLATES.length)
      ],
    [],
  );
  const [topic, setTopic] = useState(() => search.topic ?? "");
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(
        window.localStorage.getItem("lexinit:new-session:sources") || "[]",
      );
      return Array.isArray(saved)
        ? saved
            .filter((item): item is string => typeof item === "string")
            .slice(0, 5)
        : [];
    } catch {
      return [];
    }
  });
  const [difficulty, setDifficulty] = useState("Medium");
  const [mode, setMode] = useState<Mode>("quick");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState<"pdf" | "image" | "">("");
  const [listening, setListening] = useState(false);
  const [status, setStatus] = useState("");
  const [completionVisible, setCompletionVisible] = useState(false);
  const [error, setError] = useState("");
  const pdfInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const completedRunRef = useRef<string | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);
  const [generationActionBusy, setGenerationActionBusy] = useState(false);
  const generation = useGenerationRun("lexinit:generation:new-session");
  const dismissGeneration = generation.dismiss;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const topicPlaceholder =
    uploading === "pdf"
      ? "Reading PDF..."
      : uploading === "image"
        ? "Reading image..."
        : listening
          ? "Listening..."
          : "Enter a topic for your course...";

  useEffect(() => {
    // Remove a draft saved by earlier versions so a new course always starts blank.
    window.localStorage.removeItem("lexinit:new-session:topic");
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      "lexinit:new-session:sources",
      JSON.stringify(selectedSourceIds),
    );
  }, [selectedSourceIds]);

  const openSession = useCallback(
    async (sessionId: string) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["me"] }),
        queryClient.invalidateQueries({ queryKey: ["sessions"] }),
      ]);
      navigate({ to: "/app/session/$id/path", params: { id: sessionId } });
    },
    [navigate, queryClient],
  );

  const completeAndOpenSession = useCallback(
    async (sessionId: string) => {
      setStatus("Content generation complete. 100%");
      await new Promise((resolve) => window.setTimeout(resolve, 700));
      setCompletionVisible(true);
      setStatus("");
      await new Promise((resolve) => window.setTimeout(resolve, 1600));
      await openSession(sessionId);
    },
    [openSession],
  );

  useEffect(() => {
    const run = generation.run;
    if (!run) return;
    setStatus(`${run.message} ${run.progress}%`);
    if (["queued", "running", "repairing", "saving"].includes(run.status)) {
      setLoading(true);
      setError("");
      return;
    }
    setLoading(false);
    if (run.status === "failed") {
      setError(run.error?.message || run.message || "Generation failed.");
      return;
    }
    if (run.status === "cancelled") {
      setStatus("Generation cancelled.");
      return;
    }
    if (
      run.status === "completed" &&
      run.session_id &&
      completedRunRef.current !== run.id
    ) {
      completedRunRef.current = run.id;
      idempotencyKeyRef.current = null;
      window.localStorage.removeItem("lexinit:new-session:topic");
      window.localStorage.removeItem("lexinit:new-session:sources");
      dismissGeneration();
      void completeAndOpenSession(run.session_id);
    }
  }, [completeAndOpenSession, dismissGeneration, generation.run]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setStatus("");
    setCompletionVisible(false);

    if (!topic.trim()) {
      setError("Enter a topic first.");
      return;
    }

    setLoading(true);
    let runStarted = false;
    try {
      idempotencyKeyRef.current ??= createIdempotencyKey("new-session");
      const result = await requestJson<SubmitTopicResult>(
        "/api/v1/generation-runs",
        {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKeyRef.current },
          json: {
            topic,
            difflevel: difficulty,
            mode: mode === "deep" ? "Pro Reasoning" : "Basic",
            source_ids: selectedSourceIds,
            ...(search.assessment_submission_id
              ? { assessment_submission_id: search.assessment_submission_id }
              : {}),
          },
        },
      );

      if (result.success === false) {
        throw new Error(result.message || "Could not start generation.");
      }
      if (result.session_id) {
        idempotencyKeyRef.current = null;
        window.localStorage.removeItem("lexinit:new-session:topic");
        window.localStorage.removeItem("lexinit:new-session:sources");
        await completeAndOpenSession(result.session_id);
        return;
      }
      if (result.job_id) {
        runStarted = true;
        generation.start(result.job_id);
        setStatus(result.message || "Generation queued.");
        return;
      }
      throw new Error("The course was not created. Please try again.");
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create the course."));
    } finally {
      if (!runStarted) setLoading(false);
    }
  };

  const handleGenerationAction = async (action: "cancel" | "retry") => {
    setGenerationActionBusy(true);
    setError("");
    try {
      await (action === "cancel" ? generation.cancel() : generation.retry());
    } catch (err) {
      setError(apiErrorMessage(err, `Could not ${action} generation.`));
    } finally {
      setGenerationActionBusy(false);
    }
  };

  const uploadSource = async (file: File, kind: "pdf" | "image") => {
    setError("");
    setStatus(kind === "pdf" ? "Reading PDF..." : "Reading image...");
    setUploading(kind);

    try {
      const result = await uploadLearningSource(file);
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      if (result.source.status === "failed") {
        throw new Error(
          result.source.error_message || "Could not read that source.",
        );
      }
      setSelectedSourceIds((current) =>
        current.includes(result.source.source_id)
          ? current
          : [...current, result.source.source_id].slice(0, 5),
      );
      if (!topic.trim() && result.source.suggested_topic) {
        setTopic(result.source.suggested_topic);
      }
      setStatus("Source ready. Review the topic, then create your course.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not read that file.",
      );
      setStatus("");
    } finally {
      setUploading("");
    }
  };

  const handleFileChange =
    (kind: "pdf" | "image") =>
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      await uploadSource(file, kind);
    };

  const toggleListening = () => {
    setError("");

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      setStatus("");
      return;
    }

    const SpeechRecognition =
      (
        window as typeof window & {
          SpeechRecognition?: SpeechRecognitionConstructor;
          webkitSpeechRecognition?: SpeechRecognitionConstructor;
        }
      ).SpeechRecognition ??
      (
        window as typeof window & {
          webkitSpeechRecognition?: SpeechRecognitionConstructor;
        }
      ).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0]?.transcript ?? "";
      }
      setTopic(transcript.trim());
    };
    recognition.onerror = () => {
      setListening(false);
      setError("Could not capture voice input. Try again.");
      setStatus("");
    };
    recognition.onend = () => {
      setListening(false);
      setStatus((current) => (current === "Listening..." ? "" : current));
    };
    recognitionRef.current = recognition;
    setListening(true);
    setStatus("Listening...");
    recognition.start();
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 pt-2 lg:pt-3">
      <AnimatePresence>
        {completionVisible && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center bg-background/80 px-6 backdrop-blur-xl"
          >
            <motion.div
              initial={{ opacity: 0, y: 18, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -12, scale: 0.98 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="w-full max-w-md rounded-[28px] border border-border bg-card p-8 text-center shadow-[var(--shadow-elegant)]"
            >
              <div className="relative mx-auto h-20 w-20">
                <motion.div
                  initial={{ scale: 0.65, opacity: 0 }}
                  animate={{ scale: 1.3, opacity: 0 }}
                  transition={{ duration: 0.8, ease: "easeOut", delay: 0.12 }}
                  className="absolute inset-0 rounded-full bg-accent/35"
                />
                <motion.div
                  initial={{ scale: 0.55, opacity: 0, rotate: -12 }}
                  animate={{ scale: 1, opacity: 1, rotate: 0 }}
                  transition={{
                    type: "spring",
                    stiffness: 420,
                    damping: 20,
                    delay: 0.08,
                  }}
                  className="relative grid h-20 w-20 place-items-center rounded-full bg-accent text-accent-foreground shadow-[0_12px_32px_color-mix(in_oklab,var(--accent)_35%,transparent)]"
                >
                  <motion.div
                    initial={{ scale: 0, rotate: -25 }}
                    animate={{ scale: 1, rotate: 0 }}
                    transition={{
                      type: "spring",
                      stiffness: 520,
                      damping: 24,
                      delay: 0.25,
                    }}
                  >
                    <Check className="h-10 w-10" strokeWidth={3.5} />
                  </motion.div>
                </motion.div>
              </div>
              <h2 className="mt-5 font-display text-3xl tracking-tight text-foreground">
                Course created
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Your course is ready and saved. Opening its learning path now.
              </p>
              <div className="mt-6 h-2 overflow-hidden rounded-full bg-muted">
                <motion.div
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 0.7, ease: "easeOut" }}
                  className="h-full rounded-full bg-accent"
                />
              </div>
              <div className="mt-3 text-xs font-medium uppercase tracking-[0.2em] text-accent">
                100% complete
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.header
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: "easeOut" }}
        className="mx-auto max-w-3xl pt-0"
      >
        <div className="text-center">
          <h1 className="font-display text-4xl tracking-tight text-foreground sm:text-5xl lg:text-6xl">
            {greeting.before}
            <strong className="font-semibold">{firstName}</strong>
            {greeting.after}
          </h1>
          <p className="mx-auto mt-4 max-w-3xl text-base leading-7 text-muted-foreground sm:text-lg">
            Start with a topic, source, image, or voice note.
          </p>
        </div>
      </motion.header>

      {search.assessment_submission_id && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mx-auto flex max-w-3xl items-start gap-3 rounded-2xl border border-accent/35 bg-accent/10 p-4"
        >
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="font-semibold text-foreground">
              Focused follow-up
            </div>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Generated from weak areas identified in{" "}
              <span className="font-medium text-foreground">
                {search.adaptive_from_topic || "your previous topic"}
              </span>
              . Choose the difficulty below, then create the focused course.
            </p>
            <div className="mt-2 text-xs font-medium uppercase tracking-[0.16em] text-accent">
              Selected difficulty: {difficulty}
            </div>
          </div>
        </motion.div>
      )}

      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08, duration: 0.45, ease: "easeOut" }}
        className="mx-auto max-w-3xl rounded-[22px] border border-border bg-card p-3 shadow-[var(--shadow-elegant)] transition focus-within:border-accent/50 focus-within:shadow-[var(--shadow-glow)]"
      >
        <label htmlFor="topic" className="sr-only">
          Topic or upload
        </label>
        <div className="relative">
          <input
            id="topic"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder={topicPlaceholder}
            disabled={Boolean(uploading)}
            className="h-14 w-full bg-transparent py-0 pl-3 pr-16 text-lg leading-none text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-wait"
          />
          <button
            type="submit"
            aria-label="Create course"
            disabled={loading}
            className="absolute right-1.5 top-1/2 grid h-11 w-11 shrink-0 -translate-y-1/2 place-items-center rounded-full bg-primary text-primary-foreground shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <ArrowUp className="h-5 w-5" />
            )}
          </button>
        </div>

        <div className="flex flex-col gap-3 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <ToolButton
              label="Upload PDF"
              icon={uploading === "pdf" ? Loader2 : FileUp}
              active={uploading === "pdf"}
              onClick={() => pdfInputRef.current?.click()}
              disabled={Boolean(uploading) || loading}
            />
            <ToolButton
              label="Upload image"
              icon={uploading === "image" ? Loader2 : Camera}
              active={uploading === "image"}
              onClick={() => imageInputRef.current?.click()}
              disabled={Boolean(uploading) || loading}
            />
            <ToolButton
              label={listening ? "Stop listening" : "Voice note"}
              icon={Mic}
              active={listening}
              onClick={toggleListening}
              disabled={Boolean(uploading) || loading}
            />
            <input
              ref={pdfInputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={handleFileChange("pdf")}
            />
            <input
              ref={imageInputRef}
              type="file"
              accept="image/png,image/jpeg,.png,.jpg,.jpeg"
              capture="environment"
              className="hidden"
              onChange={handleFileChange("image")}
            />
            <DifficultySelect value={difficulty} onChange={setDifficulty} />
            <ModeToggle mode={mode} setMode={setMode} />
          </div>
        </div>

        <div className="mt-4 flex min-h-6 flex-wrap items-center gap-2 px-1 text-sm text-muted-foreground">
          <Sparkles className="h-4 w-4 text-accent" />
          <span>
            Any subject, any level. Your profile tunes examples but never limits
            what you can study.
          </span>
          {status && (
            <span className="rounded-full bg-accent/10 px-3 py-1 text-accent">
              {status}
            </span>
          )}
          {error && (
            <span className="rounded-full bg-destructive/10 px-3 py-1 text-destructive">
              {error}
            </span>
          )}
        </div>
      </motion.form>

      <SourcePicker
        selected={selectedSourceIds}
        onChange={setSelectedSourceIds}
      />

      {generation.run && generation.run.status !== "completed" && (
        <GenerationProgressCard
          run={generation.run}
          busy={generationActionBusy}
          onCancel={() => void handleGenerationAction("cancel")}
          onRetry={() => void handleGenerationAction("retry")}
          onDismiss={generation.dismiss}
        />
      )}

      {/* <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.16, duration: 0.45, ease: "easeOut" }}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-display text-2xl tracking-tight text-foreground">Suggested topics</h2>
          <span className="hidden text-sm text-muted-foreground sm:inline">Tap one to load the prompt</span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SUGGESTED_TOPICS.map((suggestedTopic, index) => (
            <motion.button
              key={suggestedTopic}
              type="button"
              onClick={() => setTopic(suggestedTopic)}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + index * 0.035, duration: 0.3 }}
              className="rounded-3xl border border-border bg-card px-5 py-4 text-left transition hover:border-accent/50 hover:bg-muted/40 hover:shadow-sm"
            >
              <span className="block text-base font-medium text-foreground">{suggestedTopic}</span>
              <span className="mt-1 block text-sm text-muted-foreground">Create course</span>
            </motion.button>
          ))}
        </div>
      </motion.section> */}
    </div>
  );
}

function ToolButton({
  label,
  icon: Icon,
  active = false,
  disabled = false,
  onClick,
}: {
  label: string;
  icon: ComponentType<{ className?: string }>;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={`grid h-10 w-10 place-items-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-50 ${
        active
          ? "bg-accent/10 text-accent"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      <Icon
        className={`h-5 w-5 ${active && Icon === Loader2 ? "animate-spin" : ""}`}
      />
    </button>
  );
}

function DifficultySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-10 w-[116px] gap-2 rounded-full border-border bg-card px-4 text-sm font-medium shadow-none transition hover:bg-muted/60 focus:ring-0 focus:ring-offset-0 [&>svg]:ml-1">
        <SelectValue placeholder="Difficulty" />
      </SelectTrigger>
      <SelectContent className="rounded-2xl border-border bg-popover p-1 shadow-[var(--shadow-elegant)]">
        {["Easy", "Medium", "Hard"].map((item) => (
          <SelectItem
            key={item}
            value={item}
            className="rounded-xl px-3 py-2 text-sm font-medium focus:bg-accent/10 focus:text-foreground"
          >
            {item}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ModeToggle({
  mode,
  setMode,
}: {
  mode: Mode;
  setMode: (mode: Mode) => void;
}) {
  return (
    <div className="relative inline-grid h-10 w-[242px] grid-cols-2 rounded-full border border-border bg-card p-1 text-sm">
      <motion.span
        className="absolute bottom-1 top-1 rounded-full bg-primary shadow-sm"
        animate={{
          left: mode === "quick" ? 4 : 121,
          width: mode === "quick" ? 112 : 117,
        }}
        transition={{ type: "spring", stiffness: 420, damping: 34 }}
      />
      {(["quick", "deep"] as const).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => setMode(item)}
          className={`relative z-10 rounded-full px-4 font-medium transition ${
            mode === item
              ? "text-primary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          {item === "deep" ? "Deep Focus" : "Quick"}
        </button>
      ))}
    </div>
  );
}
