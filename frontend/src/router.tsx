import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { ApiError } from "./lib/api";

export const getRouter = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if (failureCount >= 2) return false;
          if (!(error instanceof ApiError)) return failureCount < 1;
          if ([400, 401, 403, 404, 409, 422].includes(error.status))
            return false;
          return (
            error.status === 0 || error.status === 429 || error.status >= 500
          );
        },
        retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 5_000),
      },
      mutations: { retry: false },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreload: "intent",
    defaultPreloadDelay: 80,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
