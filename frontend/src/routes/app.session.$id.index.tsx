import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/app/session/$id/")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/app/session/$id/path",
      params: { id: params.id },
      replace: true,
    });
  },
});
