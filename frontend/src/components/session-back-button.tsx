import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

export function SessionBackButton({ sessionId }: { sessionId: string }) {
  return (
    <Link
      to="/app/session/$id/path"
      params={{ id: sessionId }}
      className="inline-flex h-9 w-fit shrink-0 items-center gap-1.5 rounded-full border border-border bg-background/40 px-3 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" /> Back
    </Link>
  );
}
