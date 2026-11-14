import { useEffect, useRef, useState } from "react";

import type { VideoPlaybackState } from "@/lib/api";

type PlayerStateEvent = { data: number };
type PlayerEvent = { target: YouTubePlayer };
type YouTubePlayer = {
  destroy: () => void;
  getCurrentTime: () => number;
  getDuration: () => number;
  playVideo: () => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
};
type YouTubeNamespace = {
  Player: new (
    element: HTMLElement,
    options: {
      videoId: string;
      playerVars: Record<string, number | string>;
      events: {
        onReady: (event: PlayerEvent) => void;
        onStateChange: (event: PlayerStateEvent) => void;
      };
    },
  ) => YouTubePlayer;
};

declare global {
  interface Window {
    YT?: YouTubeNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YouTubeNamespace> | null = null;

function loadYouTubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (apiPromise) return apiPromise;
  apiPromise = new Promise<YouTubeNamespace>((resolve, reject) => {
    const previousReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previousReady?.();
      if (window.YT) resolve(window.YT);
      else reject(new Error("YouTube player API did not initialize."));
    };
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://www.youtube.com/iframe_api"]',
    );
    if (!existing) {
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      script.onerror = () =>
        reject(new Error("Could not load YouTube player."));
      document.head.appendChild(script);
    }
  });
  return apiPromise;
}

export function YouTubeLearningPlayer({
  videoId,
  resumeAt,
  autoplay = false,
  onProgress,
  onEnded,
}: {
  videoId: string;
  resumeAt: number;
  autoplay?: boolean;
  onProgress: (
    positionSeconds: number,
    durationSeconds: number,
    state: VideoPlaybackState,
    watchedSegments: Array<[number, number]>,
  ) => Promise<void> | void;
  onEnded?: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YouTubePlayer | null>(null);
  const progressRef = useRef(onProgress);
  const resumeRef = useRef(resumeAt);
  const autoplayRef = useRef(autoplay);
  const endedRef = useRef(onEnded);
  const timerRef = useRef<number | null>(null);
  const [error, setError] = useState("");
  progressRef.current = onProgress;
  endedRef.current = onEnded;

  useEffect(() => {
    let cancelled = false;
    const stopTimer = () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
    // Real viewing time: every second, if playback moved forward at a
    // plausible pace (up to 2x speed), that stretch counts as watched.
    // Seeks show up as large jumps and are ignored.
    let pending: Array<[number, number]> = [];
    let last: { position: number; at: number } | null = null;
    const sample = () => {
      const player = playerRef.current;
      if (!player) return;
      const position = player.getCurrentTime();
      const now = performance.now();
      if (last) {
        const advanced = position - last.position;
        const elapsed = (now - last.at) / 1000;
        if (advanced > 0 && advanced <= elapsed * 2.25 + 0.5) {
          const previous = pending[pending.length - 1];
          if (previous && Math.abs(previous[1] - last.position) < 0.01) {
            previous[1] = position;
          } else {
            pending.push([last.position, position]);
          }
        }
      }
      last = { position, at: now };
    };
    const save = (state: VideoPlaybackState) => {
      const player = playerRef.current;
      if (!player) return Promise.resolve();
      const duration = player.getDuration();
      if (duration <= 0) return Promise.resolve();
      sample();
      const position = player.getCurrentTime();
      const segments = pending;
      pending = [];
      return Promise.resolve(
        progressRef.current(position, duration, state, segments),
      ).catch((cause) => {
        pending = [...segments, ...pending];
        throw cause;
      });
    };
    const startTimer = () => {
      stopTimer();
      const player = playerRef.current;
      last = player
        ? { position: player.getCurrentTime(), at: performance.now() }
        : null;
      let ticks = 0;
      timerRef.current = window.setInterval(() => {
        sample();
        ticks += 1;
        if (ticks % 10 === 0) void save("playing").catch(() => undefined);
      }, 1_000);
    };

    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !hostRef.current) return;
        playerRef.current = new YT.Player(hostRef.current, {
          videoId,
          playerVars: {
            autoplay: autoplayRef.current ? 1 : 0,
            playsinline: 1,
            rel: 0,
            modestbranding: 1,
            origin: window.location.origin,
          },
          events: {
            onReady: ({ target }) => {
              const duration = target.getDuration();
              if (resumeRef.current > 0 && resumeRef.current < duration - 10) {
                target.seekTo(resumeRef.current, true);
              }
              if (autoplayRef.current) target.playVideo();
            },
            onStateChange: ({ data }) => {
              if (data === 1) startTimer();
              if (data === 2) {
                stopTimer();
                void save("paused").catch(() => undefined);
                last = null;
              }
              if (data === 0) {
                stopTimer();
                void save("ended")
                  .catch(() => undefined)
                  .finally(() => endedRef.current?.());
                last = null;
              }
            },
          },
        });
      })
      .catch((cause) => {
        setError(
          cause instanceof Error ? cause.message : "Could not load the player.",
        );
      });

    return () => {
      cancelled = true;
      stopTimer();
      // Keep the last few seconds watched before leaving this video.
      if (pending.length) void save("paused").catch(() => undefined);
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [videoId]);

  if (error) {
    return (
      <div className="grid aspect-video place-items-center rounded-2xl border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <div className="aspect-video overflow-hidden rounded-2xl bg-black shadow-sm">
      <div ref={hostRef} className="h-full w-full" />
    </div>
  );
}
