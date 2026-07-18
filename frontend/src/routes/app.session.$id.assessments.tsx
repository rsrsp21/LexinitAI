import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { BrainCircuit, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { AdaptiveAssessment } from "@/components/adaptive-assessment";
import { AssessmentResult } from "@/components/assessment-result";
import { SessionBackButton } from "@/components/session-back-button";
import { useSession } from "@/hooks/use-session";
import {
  mcqs,
  oneWordQuestions,
  sessionTitle,
  trueFalseQuestions,
} from "@/lib/session-utils";
import { preloadCoursePage } from "@/lib/route-prefetch";

export const Route = createFileRoute("/app/session/$id/assessments")({
  beforeLoad: ({ context, params }) =>
    preloadCoursePage(context.queryClient, params.id, { session: true }),
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
    submission:
      typeof search.submission === "string" ? search.submission : undefined,
    type:
      search.type === "mcq" ||
      search.type === "truefalse" ||
      search.type === "oneword"
        ? search.type
        : undefined,
    reattempt:
      typeof search.reattempt === "string" ? search.reattempt : undefined,
  }),
  head: () => ({ meta: [{ title: "Assessments - Lexinit" }] }),
  component: Assessments,
});

const TABS = ["Multiple Choice", "True/False", "One-word Answer"] as const;
type Tab = (typeof TABS)[number];

function Assessments() {
  const { id } = Route.useParams();
  const { module, submission, type, reattempt } = Route.useSearch();
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useSession(id);
  const session = data?.session;
  const moduleTitle = session?.curriculum?.modules.find(
    (item) => item.module_id === module,
  )?.title;
  const questions = useMemo(() => {
    const filterModule = <T extends { moduleId?: string }>(items: T[]) =>
      module ? items.filter((item) => item.moduleId === module) : items;
    return {
      mcq: filterModule(mcqs(session)),
      trueFalse: filterModule(trueFalseQuestions(session)),
      oneWord: filterModule(oneWordQuestions(session)),
    };
  }, [module, session]);
  const [tab, setTab] = useState<Tab>(
    type === "truefalse"
      ? "True/False"
      : type === "oneword"
        ? "One-word Answer"
        : "Multiple Choice",
  );
  const [showAssessments, setShowAssessments] = useState(true);

  useEffect(() => {
    if (type === "truefalse") setTab("True/False");
    else if (type === "oneword") setTab("One-word Answer");
    else if (type === "mcq") setTab("Multiple Choice");
  }, [type]);

  const selectAssessment = (nextTab: Tab) => {
    setTab(nextTab);
    void navigate({
      to: "/app/session/$id/assessments",
      params: { id },
      search: {
        module,
        submission: undefined,
        reattempt: undefined,
        type:
          nextTab === "True/False"
            ? "truefalse"
            : nextTab === "One-word Answer"
              ? "oneword"
              : "mcq",
      },
      replace: true,
    });
  };

  return (
    <div>
      <article className="flex h-[calc(100svh-190px)] min-h-[440px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm lg:h-[calc(100vh-148px)] lg:min-h-[560px]">
        <header className="shrink-0 border-b border-border p-5 sm:p-6">
          <div className="flex min-w-0 items-center gap-3">
            <SessionBackButton sessionId={id} />
            <BrainCircuit className="h-8 w-8 shrink-0 text-accent" />
            <h1 className="min-w-0 font-display text-3xl leading-[1.05] tracking-tight sm:text-4xl">
              {isLoading ? "Loading assessments" : "Assessments"}
            </h1>
          </div>

          {!isError ? (
            <div className="mt-4 flex flex-wrap gap-2 text-sm text-muted-foreground">
              <span className="rounded-full border border-border bg-background/40 px-3 py-1.5">
                <span className="font-medium text-foreground">Topic:</span>{" "}
                {sessionTitle(session)}
              </span>
              <span className="rounded-full border border-accent/25 bg-accent/10 px-3 py-1.5 text-accent">
                <span className="font-medium">Module:</span>{" "}
                {moduleTitle || "All modules"}
              </span>
              <span className="rounded-full border border-border bg-background/40 px-3 py-1.5">
                <span className="font-medium text-foreground">Type:</span> {tab}
              </span>
            </div>
          ) : (
            <p className="mt-3 text-sm text-destructive">{error.message}</p>
          )}
        </header>

        <div className="flex min-h-0 flex-1">
          <AnimatePresence initial={false}>
            {showAssessments && (
              <motion.nav
                key="assessments-nav"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 240, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className="hidden shrink-0 overflow-hidden border-r border-border bg-background/30 lg:block"
              >
                <div className="flex h-12 w-[240px] items-center gap-2 border-b border-border px-3">
                  <button
                    type="button"
                    onClick={() => setShowAssessments(false)}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    aria-label="Hide assessment list"
                  >
                    <PanelLeftClose className="h-4 w-4" />
                  </button>
                  <h2 className="truncate text-sm font-semibold text-foreground">
                    Assessments
                  </h2>
                </div>
                <AssessmentNavigation tab={tab} onSelect={selectAssessment} />
              </motion.nav>
            )}
          </AnimatePresence>

          <section className="app-scrollbar min-h-0 flex-1 overflow-y-auto bg-background/50 p-5 sm:p-7">
            <AnimatePresence initial={false}>
              {!showAssessments && (
                <motion.button
                  type="button"
                  onClick={() => setShowAssessments(true)}
                  initial={{ opacity: 0, scale: 0.92, y: -4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.92, y: -4 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                  className="mb-4 grid h-10 w-10 place-items-center rounded-full border border-border bg-card text-muted-foreground shadow-sm transition hover:bg-muted hover:text-foreground"
                  aria-label="Show assessment list"
                >
                  <PanelLeftOpen className="h-4 w-4" />
                </motion.button>
              )}
            </AnimatePresence>

            <div className="lg:hidden">
              {showAssessments && (
                <div className="mb-4 overflow-hidden rounded-xl border border-border bg-background/40">
                  <div className="flex h-12 items-center gap-2 border-b border-border px-3">
                    <button
                      type="button"
                      onClick={() => setShowAssessments(false)}
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                      aria-label="Hide assessment list"
                    >
                      <PanelLeftClose className="h-4 w-4" />
                    </button>
                    <h2 className="truncate text-sm font-semibold text-foreground">
                      Assessments
                    </h2>
                  </div>
                  <AssessmentNavigation
                    tab={tab}
                    onSelect={selectAssessment}
                    compact
                  />
                </div>
              )}
            </div>

            <div className="mx-auto max-w-4xl rounded-xl border border-border bg-card/80 p-5 sm:p-7">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-3xl tracking-tight sm:text-4xl">
                  {submission ? "Assessment result" : tab}
                </h2>
              </div>
              <div className="mt-7">
                {isLoading && (
                  <EmptyState text="Loading assessment questions." />
                )}
                {isError && <EmptyState text={error.message} />}
                {!isLoading && !isError && submission && (
                  <AssessmentResult
                    submissionId={submission}
                    sessionId={id}
                    moduleId={module}
                  />
                )}
                {!isLoading && !isError && !submission && (
                  <AdaptiveAssessment
                    key={`adaptive-${id}-${module || "all"}-${tab}-${reattempt || "continue"}`}
                    sessionId={id}
                    moduleId={module}
                    forceNewToken={reattempt}
                    assessmentType={
                      tab === "Multiple Choice"
                        ? "mcq"
                        : tab === "True/False"
                          ? "truefalse"
                          : "oneword"
                    }
                    availableQuestions={
                      tab === "Multiple Choice"
                        ? questions.mcq.length
                        : tab === "True/False"
                          ? questions.trueFalse.length
                          : questions.oneWord.length
                    }
                  />
                )}
              </div>
            </div>
          </section>
        </div>
      </article>
    </div>
  );
}

function AssessmentNavigation({
  tab,
  onSelect,
  compact = false,
}: {
  tab: Tab;
  onSelect: (tab: Tab) => void;
  compact?: boolean;
}) {
  return (
    <div
      className={`app-scrollbar overflow-y-auto p-3 ${compact ? "max-h-56" : "h-full min-h-0 w-[240px]"}`}
    >
      <ul className="space-y-1">
        {TABS.map((item) => (
          <li key={item}>
            <button
              onClick={() => onSelect(item)}
              className={`w-full rounded-xl px-3 py-2.5 text-left text-sm leading-5 transition ${
                tab === item
                  ? "bg-accent/10 font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              {item}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/60 p-5 text-sm text-muted-foreground">
      {text}
    </div>
  );
}
