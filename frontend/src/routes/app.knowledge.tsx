import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Clock, Network } from "lucide-react";

import { getKnowledgeMap, type KnowledgeConcept } from "@/lib/api";

export const Route = createFileRoute("/app/knowledge")({
  head: () => ({ meta: [{ title: "Knowledge map - Lexinit" }] }),
  component: KnowledgeMapPage,
});

const STATUS: Record<
  KnowledgeConcept["status"],
  { label: string; tile: string; dot: string }
> = {
  mastered: {
    label: "Mastered",
    tile: "border-emerald-500/40 bg-emerald-500/15",
    dot: "bg-emerald-500",
  },
  proficient: {
    label: "Proficient",
    tile: "border-emerald-500/25 bg-emerald-500/8",
    dot: "bg-emerald-400",
  },
  developing: {
    label: "Developing",
    tile: "border-amber-500/35 bg-amber-500/10",
    dot: "bg-amber-500",
  },
  weak: {
    label: "Needs work",
    tile: "border-destructive/35 bg-destructive/8",
    dot: "bg-destructive",
  },
  fading: {
    label: "Fading",
    tile: "border-dashed border-amber-500/50 bg-amber-500/5",
    dot: "bg-amber-300",
  },
  new: {
    label: "Not practised",
    tile: "border-border bg-background/45",
    dot: "bg-muted-foreground/40",
  },
};

const LEGEND: KnowledgeConcept["status"][] = [
  "mastered",
  "proficient",
  "developing",
  "weak",
  "fading",
  "new",
];

function KnowledgeMapPage() {
  const map = useQuery({
    queryKey: ["knowledge-map"],
    queryFn: getKnowledgeMap,
    staleTime: 30_000,
  });
  const summary = map.data?.summary;

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12 pt-2">
      <header>
        <h1 className="flex items-center gap-3 font-display text-4xl tracking-tight sm:text-5xl">
          <Network className="h-8 w-8 shrink-0 text-accent" /> Knowledge map
        </h1>
        <p className="mt-3 max-w-2xl text-base text-muted-foreground">
          Every concept you have studied, coloured by how well you know it now.
          Mastery fades without practice, so concepts drift back until you
          review them.
        </p>
      </header>

      {map.isLoading && <Panel>Loading your knowledge map.</Panel>}
      {map.isError && <Panel>{map.error.message}</Panel>}

      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Concepts" value={summary.concepts} />
          <Stat label="Known well" value={summary.strong} />
          <Stat label="Fading" value={summary.fading} />
          <Stat label="Due for review" value={summary.due} />
        </div>
      )}

      {map.data && (
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
          {LEGEND.map((status) => (
            <span key={status} className="inline-flex items-center gap-1.5">
              <span
                className={`h-2.5 w-2.5 rounded-full ${STATUS[status].dot}`}
              />
              {STATUS[status].label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3 w-3" /> Due for review
          </span>
        </div>
      )}

      {map.data && map.data.courses.length === 0 && (
        <Panel>
          Create a course and answer a few questions to start your map.
        </Panel>
      )}

      {map.data?.courses.map((course) => (
        <section
          key={course.session_id}
          className="rounded-[24px] border border-border bg-card p-5 shadow-sm sm:p-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl tracking-tight">
              {course.topic}
            </h2>
            <Link
              to="/app/session/$id/path"
              params={{ id: course.session_id }}
              className="text-sm font-semibold text-accent hover:underline"
            >
              Open course
            </Link>
          </div>
          <div className="mt-4 space-y-4">
            {course.modules.map((module) => (
              <div key={module.module_id}>
                <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {module.title}
                </h3>
                <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {module.concepts.map((concept) => (
                    <ConceptTile
                      key={concept.concept_id}
                      concept={concept}
                      sessionId={course.session_id}
                      moduleId={module.module_id}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function ConceptTile({
  concept,
  sessionId,
  moduleId,
}: {
  concept: KnowledgeConcept;
  sessionId: string;
  moduleId: string;
}) {
  const style = STATUS[concept.status];
  const percent =
    concept.current_mastery === null
      ? null
      : Math.round(concept.current_mastery * 100);
  return (
    <Link
      to="/app/session/$id/materials"
      params={{ id: sessionId }}
      search={{ module: moduleId }}
      title={
        concept.status === "fading" && concept.peak_mastery !== null
          ? `Was ${Math.round(concept.peak_mastery * 100)}%, now ${percent}% without practice`
          : style.label
      }
      className={`flex items-center gap-3 rounded-xl border px-3.5 py-3 transition hover:-translate-y-0.5 hover:shadow-sm ${style.tile}`}
    >
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${style.dot}`} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">
          {concept.label}
        </span>
        <span className="block text-xs text-muted-foreground">
          {style.label}
          {percent !== null ? ` · ${percent}%` : ""}
        </span>
      </span>
      {concept.due && (
        <Clock
          className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-300"
          aria-label="Due for review"
        />
      )}
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="font-display text-3xl tracking-tight">{value}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground">
      {children}
    </div>
  );
}
