import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import {
  cancelGenerationRun,
  getActiveGenerationRuns,
  getGenerationRun,
  retryGenerationRun,
} from "@/lib/api";

const ACTIVE_STATUSES = new Set(["queued", "running", "repairing", "saving"]);

export function useGenerationRun(
  storageKey: string,
  { recoverActive = true }: { recoverActive?: boolean } = {},
) {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(storageKey);
  });
  const activeQuery = useQuery({
    queryKey: ["generation-runs", "active"],
    queryFn: getActiveGenerationRuns,
    refetchInterval: 4_000,
    staleTime: 1_000,
  });

  useEffect(() => {
    if (!recoverActive || runId || !activeQuery.data?.runs.length) return;
    const latest = activeQuery.data.runs[0];
    setRunId(latest.id);
    window.localStorage.setItem(storageKey, latest.id);
  }, [activeQuery.data?.runs, recoverActive, runId, storageKey]);

  const runQuery = useQuery({
    queryKey: ["generation-run", runId],
    queryFn: () => getGenerationRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return !status || ACTIVE_STATUSES.has(status) ? 2_000 : false;
    },
    retry: (failureCount, error) =>
      failureCount < 3 &&
      !(error instanceof Error && error.message.includes("not found")),
  });

  const start = useCallback(
    (nextRunId: string) => {
      setRunId(nextRunId);
      window.localStorage.setItem(storageKey, nextRunId);
      void queryClient.invalidateQueries({
        queryKey: ["generation-runs", "active"],
      });
    },
    [queryClient, storageKey],
  );

  const dismiss = useCallback(() => {
    setRunId(null);
    window.localStorage.removeItem(storageKey);
  }, [storageKey]);

  const cancel = useCallback(async () => {
    if (!runId) return;
    await cancelGenerationRun(runId);
    await Promise.all([runQuery.refetch(), activeQuery.refetch()]);
  }, [activeQuery, runId, runQuery]);

  const retry = useCallback(async () => {
    if (!runId) return;
    await retryGenerationRun(runId);
    await Promise.all([runQuery.refetch(), activeQuery.refetch()]);
  }, [activeQuery, runId, runQuery]);

  return {
    runId,
    run: runQuery.data,
    isLoading: Boolean(runId) && runQuery.isLoading,
    error: runQuery.error,
    start,
    dismiss,
    cancel,
    retry,
  };
}
