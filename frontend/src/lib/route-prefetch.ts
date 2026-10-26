import type { QueryClient } from "@tanstack/react-query";

import { getCourse, getSession, getVideoCatalog } from "@/lib/api";

export async function preloadCoursePage(
  queryClient: QueryClient,
  sessionId: string,
  options: { session?: boolean; videos?: boolean } = {},
) {
  const tasks: Array<Promise<unknown>> = [
    queryClient
      .ensureQueryData({
        queryKey: ["course", sessionId],
        queryFn: () => getCourse(sessionId),
        staleTime: 5_000,
      })
      .catch(() => undefined),
  ];

  if (options.session) {
    tasks.push(
      queryClient
        .ensureQueryData({
          queryKey: ["session", sessionId],
          queryFn: () => getSession(sessionId),
          staleTime: 15_000,
        })
        .catch(() => undefined),
    );
  }

  if (options.videos) {
    tasks.push(
      queryClient
        .ensureQueryData({
          queryKey: ["video-catalog", sessionId],
          queryFn: () => getVideoCatalog(sessionId),
          staleTime: 5 * 60 * 1_000,
        })
        .catch(() => undefined),
    );
  }

  await Promise.all(tasks);
}
