import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { getMe } from "@/lib/api";

export const Route = createFileRoute("/app")({
  head: () => ({
    meta: [
      { title: "Learning Dashboard — Lexinit" },
      { name: "description", content: "Your Lexinit learning dashboard." },
    ],
  }),
  beforeLoad: async ({ context }) => {
    let me;
    try {
      me = await context.queryClient.ensureQueryData({
        queryKey: ["me"],
        queryFn: getMe,
        staleTime: 30_000,
      });
    } catch {
      throw redirect({ to: "/login" });
    }
    if (me.user.profile_complete === false) {
      throw redirect({ to: "/onboarding" });
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});
