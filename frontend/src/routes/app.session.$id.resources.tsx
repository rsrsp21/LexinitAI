import { createFileRoute } from "@tanstack/react-router";
import { BookOpen, ExternalLink, Globe } from "lucide-react";
import type { ComponentType } from "react";

import { useSession } from "@/hooks/use-session";
import { resources, sessionTitle } from "@/lib/session-utils";
import { SessionBackButton } from "@/components/session-back-button";

export const Route = createFileRoute("/app/session/$id/resources")({
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
  }),
  head: () => ({ meta: [{ title: "Additional Resources - Lexinit" }] }),
  component: Resources,
});

function Resources() {
  const { id } = Route.useParams();
  const { module } = Route.useSearch();
  const { data, isLoading, isError, error } = useSession(id);
  const session = data?.session;
  const items = resources(session);
  const moduleTitle = session?.curriculum?.modules.find(
    (item) => item.module_id === module,
  )?.title;

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <div className="flex min-w-0 items-center gap-3">
        <SessionBackButton sessionId={id} />
        <h1 className="min-w-0 font-display text-3xl leading-[1.05] tracking-tight sm:text-4xl">
          {isLoading ? "Loading Additional Resources" : "Additional Resources"}
        </h1>
      </div>
      {!isError && (
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

      {isLoading || isError || items.length === 0 ? (
        <div className="mt-8 rounded-xl border border-border bg-background p-6 text-sm text-muted-foreground">
          {isLoading
            ? "Loading resources."
            : isError
              ? error.message
              : "No additional resources are available in this course yet."}
        </div>
      ) : (
        <div className="mt-8 grid gap-6 md:grid-cols-2">
          <ResourceGroup
            title="Recommended"
            icon={BookOpen}
            items={items.slice(0, Math.ceil(items.length / 2))}
          />
          <ResourceGroup
            title="Explore More"
            icon={Globe}
            items={items.slice(Math.ceil(items.length / 2))}
          />
        </div>
      )}
    </div>
  );
}

function ResourceGroup({
  title,
  icon: Icon,
  items,
}: {
  title: string;
  icon: ComponentType<{ className?: string }>;
  items: ReturnType<typeof resources>;
}) {
  if (items.length === 0) return null;

  return (
    <div className="rounded-xl border border-border bg-background p-6">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-secondary text-foreground">
          <Icon className="h-5 w-5" />
        </div>
        <h2 className="font-display text-2xl tracking-tight">{title}</h2>
      </div>
      <ul className="mt-5 space-y-2">
        {items.map((item) => (
          <li key={`${item.title}-${item.url}`}>
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="group flex items-start justify-between gap-4 rounded-lg border border-transparent px-3 py-3 transition hover:border-accent/40 hover:bg-accent/5"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{item.title}</div>
                <div className="mt-0.5 truncate text-xs text-muted-foreground">
                  {item.by}
                </div>
              </div>
              <ExternalLink className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition group-hover:text-accent" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
