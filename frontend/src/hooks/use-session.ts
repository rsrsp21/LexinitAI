import { useQuery } from "@tanstack/react-query";

import { getSession } from "@/lib/api";

export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId),
    retry: false,
    enabled: Boolean(sessionId),
  });
}
