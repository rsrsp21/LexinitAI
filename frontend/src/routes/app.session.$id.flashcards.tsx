import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Layers3, RotateCw } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { useSession } from "@/hooks/use-session";
import { SessionBackButton } from "@/components/session-back-button";
import { flashcards, sessionTitle } from "@/lib/session-utils";
import { preloadCoursePage } from "@/lib/route-prefetch";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCourse, setCourseActivity } from "@/lib/api";
import { CheckCircle2, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/app/session/$id/flashcards")({
  beforeLoad: ({ context, params }) =>
    preloadCoursePage(context.queryClient, params.id, { session: true }),
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
  }),
  head: () => ({ meta: [{ title: "Flashcards - Lexinit" }] }),
  component: Flashcards,
});

function Flashcards() {
  const { id } = Route.useParams();
  const { module } = Route.useSearch();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useSession(id);
  const session = data?.session;
  const moduleTitle = session?.curriculum?.modules.find(
    (item) => item.module_id === module,
  )?.title;
  const cards = useMemo(() => {
    const all = flashcards(session);
    return module ? all.filter((card) => card.moduleId === module) : all;
  }, [module, session]);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [slideDirection, setSlideDirection] = useState<1 | -1>(1);
  const card = cards[index];

  const course = useQuery({
    queryKey: ["course", id],
    queryFn: () => getCourse(id!),
    enabled: Boolean(id),
  });

  const currentModule = course.data?.modules.find(m => m.module_id === module);
  const activity = currentModule?.activities.find(a => a.type === "flashcards");

  const markCompletedMutation = useMutation({
    mutationFn: () => setCourseActivity(id!, activity!.activity_id, "completed"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course", id] });
    }
  });

  useEffect(() => {
    if (index >= cards.length) {
      setIndex(Math.max(cards.length - 1, 0));
      setFlipped(false);
    }
  }, [cards.length, index]);

  const go = (direction: 1 | -1) => {
    if (cards.length === 0) return;
    const nextIndex = Math.min(
      Math.max(index + direction, 0),
      cards.length - 1,
    );
    if (nextIndex === index) return;

    setSlideDirection(direction);
    setFlipped(false);
    setIndex(nextIndex);
  };

  return (
    <div>
      <div className="rounded-2xl border border-border bg-card p-8 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <SessionBackButton sessionId={id} />
            <Layers3 className="h-8 w-8 shrink-0 text-accent" />
            <h1 className="font-display text-4xl leading-tight tracking-tight sm:text-5xl">
              Flashcards
            </h1>
          </div>
          <div className="text-sm text-muted-foreground">
            Card{" "}
            <span className="font-medium text-foreground">
              {cards.length ? index + 1 : 0}
            </span>{" "}
            / {cards.length}
          </div>
        </div>

        {!isLoading && !isError && (
          <div className="mt-4 flex flex-wrap gap-2 text-sm text-muted-foreground">
            <span className="rounded-full border border-border bg-background/40 px-3 py-1.5">
              <span className="font-medium text-foreground">Topic:</span>{" "}
              {sessionTitle(session)}
            </span>
            <span className="rounded-full border border-accent/25 bg-accent/10 px-3 py-1.5 text-accent">
              <span className="font-medium">Module:</span>{" "}
              {moduleTitle || "All modules"}
            </span>
          </div>
        )}

        {isLoading || isError || !card ? (
          <div className="mt-8 rounded-xl border border-border bg-background p-6 text-sm text-muted-foreground">
            {isLoading
              ? "Loading flashcards."
              : isError
                ? error.message
                : "No flashcards are available in this course yet."}
          </div>
        ) : (
          <>
            <div className="mt-8 flex items-center justify-center gap-3 sm:gap-5">
              <button
                onClick={() => go(-1)}
                disabled={index === 0}
                aria-label="Previous"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-border text-muted-foreground transition hover:border-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:border-border disabled:hover:text-muted-foreground sm:h-12 sm:w-12"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>

              <div className="relative h-[360px] w-full max-w-3xl flex-1 [perspective:1200px] sm:h-[400px]">
                {cards.length - index > 2 && <FlashcardStackLayer depth={2} />}
                {cards.length - index > 1 && <FlashcardStackLayer depth={1} />}

                <div className="absolute inset-0 z-20 overflow-visible rounded-2xl">
                  <AnimatePresence
                    initial={false}
                    custom={slideDirection}
                    mode="sync"
                  >
                    <motion.button
                      key={card.id || index}
                      custom={slideDirection}
                      variants={{
                        enter: (direction: 1 | -1) =>
                          direction === 1
                            ? {
                                opacity: 0.45,
                                x: 34,
                                y: 18,
                                rotate: 3.2,
                                scale: 0.94,
                              }
                            : {
                                opacity: 0,
                                x: -280,
                                y: -18,
                                rotate: -10,
                                scale: 0.97,
                              },
                        center: {
                          opacity: 1,
                          x: 0,
                          y: 0,
                          rotate: -0.9,
                          scale: 1,
                        },
                        exit: (direction: 1 | -1) =>
                          direction === 1
                            ? {
                                opacity: [1, 1, 0],
                                x: [0, 300, 42],
                                y: [0, -22, 22],
                                rotate: [-0.9, 11, 3.5],
                                scale: [1, 0.98, 0.93],
                              }
                            : {
                                opacity: [1, 0.85, 0],
                                x: [0, 250, 38],
                                y: [0, -16, 20],
                                rotate: [-0.9, 9, 3.2],
                                scale: [1, 0.97, 0.94],
                              },
                      }}
                      initial="enter"
                      animate="center"
                      exit="exit"
                      transition={{ duration: 0.58, ease: [0.22, 1, 0.36, 1] }}
                      onClick={() => setFlipped((current) => !current)}
                      aria-label={
                        flipped
                          ? "Show flashcard question"
                          : "Show flashcard answer"
                      }
                      className="group absolute inset-0 h-full w-full bg-transparent text-left drop-shadow-[0_18px_22px_rgba(15,23,42,0.12)]"
                    >
                      <motion.div
                        className="relative h-full w-full [transform-style:preserve-3d]"
                        animate={{ rotateY: flipped ? 180 : 0 }}
                        transition={{
                          duration: 0.55,
                          ease: [0.22, 1, 0.36, 1],
                        }}
                      >
                        <FlashcardFace
                          label="Question"
                          content={card.question}
                        />
                        <FlashcardFace
                          label="Answer"
                          content={card.answer}
                          back
                        />
                      </motion.div>
                    </motion.button>
                  </AnimatePresence>
                </div>
              </div>

              <button
                onClick={() => go(1)}
                disabled={index === cards.length - 1}
                aria-label="Next"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-border text-muted-foreground transition hover:border-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:border-border disabled:hover:text-muted-foreground sm:h-12 sm:w-12"
              >
                <ArrowRight className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-9 h-1.5 overflow-hidden rounded-full bg-muted">
              <motion.div
                className="h-full bg-accent"
                animate={{ width: `${((index + 1) / cards.length) * 100}%` }}
                transition={{ duration: 0.35, ease: "easeOut" }}
              />
            </div>

            {index === cards.length - 1 && activity && activity.status !== "completed" && (
              <div className="mt-8 flex justify-center">
                <Button 
                   onClick={() => markCompletedMutation.mutate()} 
                   disabled={markCompletedMutation.isPending}
                   className="rounded-full px-6"
                >
                  {markCompletedMutation.isPending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                  Mark as completed
                </Button>
              </div>
            )}
            {activity?.status === "completed" && (
              <div className="mt-8 flex justify-center text-emerald-500 font-medium items-center gap-2">
                <CheckCircle2 className="h-5 w-5" /> Completed
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function FlashcardStackLayer({ depth }: { depth: 1 | 2 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 0, scale: 0.98 }}
      animate={{
        opacity: depth === 1 ? 0.96 : 0.78,
        x: depth * 17,
        y: depth * 10,
        rotate: depth * 1.65,
        scale: 1 - depth * 0.025,
      }}
      exit={{ opacity: 0, y: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 320, damping: 28 }}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 rounded-2xl border border-accent/35 bg-gradient-to-br from-card via-card to-accent/8 shadow-[0_16px_30px_rgba(15,23,42,0.13)]"
      style={{ zIndex: 20 - depth }}
    />
  );
}

function FlashcardFace({
  content,
  label,
  back = false,
}: {
  content: string;
  label: string;
  back?: boolean;
}) {
  return (
    <div
      className={`absolute inset-0 isolate flex h-full w-full items-center rounded-2xl border border-accent/30 bg-card p-8 shadow-sm transition-shadow [backface-visibility:hidden] group-hover:shadow-[var(--shadow-glow)] sm:p-12 ${
        back ? "[transform:rotateY(180deg)]" : ""
      }`}
    >
      <div className="absolute right-4 top-4 inline-flex items-center gap-1.5 rounded-full border border-border bg-background/80 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
        <RotateCw className="h-3 w-3" /> {label} · Tap to flip
      </div>
      <div className="w-full text-center font-display text-3xl leading-tight tracking-tight text-balance sm:text-4xl">
        {content}
      </div>
    </div>
  );
}
