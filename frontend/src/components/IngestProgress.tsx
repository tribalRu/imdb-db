import { useEffect, useState } from "react";
import type { IngestProgressData } from "../types/api";

interface IngestProgressProps {
  token: string;
  onIngestCompleted?: () => void;
}

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  downloading: "Downloading archive...",
  copying: "Streaming COPY into staging...",
  merging: "Merging records (Upsert)...",
  indexing: "Rebuilding search indexes...",
  completed: "Completed",
  failed: "Failed",
};

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export function IngestProgress({
  token,
  onIngestCompleted,
}: IngestProgressProps) {
  const [progress, setProgress] = useState<IngestProgressData | null>(null);
  const [showFinishedBanner, setShowFinishedBanner] = useState<boolean>(false);
  const [lastFinishedDuration, setLastFinishedDuration] = useState<number>(0);

  useEffect(() => {
    let isMounted = true;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let wasRunning = false;

    async function poll() {
      try {
        const headers: HeadersInit = { Accept: "application/json" };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const res = await fetch("/api/ingest/progress", { headers });
        if (res.ok) {
          const data = (await res.json()) as IngestProgressData;
          if (isMounted) {
            setProgress(data);

            if (wasRunning && !data.is_running && data.completed_count > 0) {
              setLastFinishedDuration(data.elapsed_seconds);
              setShowFinishedBanner(true);
              if (onIngestCompleted) {
                onIngestCompleted();
              }
            }
            wasRunning = data.is_running;
          }
          const nextInterval = data.is_running ? 1500 : 8000;
          timerId = setTimeout(poll, nextInterval);
          return;
        }
      } catch {
        // Ignore polling errors
      }
      timerId = setTimeout(poll, 8000);
    }

    poll();

    return () => {
      isMounted = false;
      if (timerId) {
        clearTimeout(timerId);
      }
    };
  }, [token, onIngestCompleted]);

  if (!progress) {
    return null;
  }

  // Active Running State
  if (progress.is_running) {
    return (
      <section className="mb-4 border border-amber-500/40 bg-panel p-4 shadow-flat">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
              </span>
              <h2 className="text-sm font-semibold tracking-wide text-zinc-100">
                Database Update in Progress
              </h2>
              <span className="rounded bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-300 border border-amber-500/30">
                {progress.completed_count} / {progress.total_count} datasets (
                {progress.percent}%)
              </span>
            </div>

            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <span>Elapsed:</span>
              <span className="font-mono text-zinc-200">
                {formatDuration(progress.elapsed_seconds)}
              </span>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full bg-gradient-to-r from-amber-600 via-amber-500 to-amber-300 transition-all duration-300"
              style={{ width: `${Math.max(progress.percent, 5)}%` }}
            />
          </div>

          {/* Items / Stages */}
          <div className="mt-1 flex flex-wrap gap-2 pt-1">
            {progress.items.map((item) => {
              const isRunning =
                item.status !== "queued" &&
                item.status !== "completed" &&
                item.status !== "failed";
              const isCompleted = item.status === "completed";
              const isFailed = item.status === "failed";
              const stageLabel = STAGE_LABELS[item.status] ?? item.status;

              return (
                <div
                  key={item.name}
                  className={`flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition ${
                    isRunning
                      ? "border-amber-500/60 bg-amber-500/10 text-amber-200"
                      : isCompleted
                        ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
                        : isFailed
                          ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                          : "border-zinc-800 bg-zinc-900/60 text-zinc-400"
                  }`}
                >
                  {isRunning ? (
                    <svg
                      className="h-3 w-3 animate-spin text-amber-400"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                      />
                    </svg>
                  ) : isCompleted ? (
                    <span className="text-emerald-400 font-bold">✓</span>
                  ) : isFailed ? (
                    <span className="text-rose-400 font-bold">✕</span>
                  ) : (
                    <span className="text-zinc-600 font-bold">○</span>
                  )}
                  <span className="font-medium">{item.name}</span>
                  {isRunning ? (
                    <span className="text-amber-300/80 italic">
                      ({stageLabel})
                    </span>
                  ) : null}
                  {item.duration ? (
                    <span className="text-zinc-500 text-[10px]">
                      {formatDuration(item.duration)}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </section>
    );
  }

  // Finished Success Banner
  if (showFinishedBanner) {
    return (
      <section className="mb-4 flex items-center justify-between border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-300 shadow-flat">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-emerald-500/20 p-1 text-emerald-400 font-bold">
            ✓
          </span>
          <span>
            Database ingest completed successfully in{" "}
            <strong>{formatDuration(lastFinishedDuration)}</strong>.
          </span>
        </div>
        <button
          type="button"
          onClick={() => setShowFinishedBanner(false)}
          className="text-emerald-400 hover:text-emerald-200"
        >
          ✕
        </button>
      </section>
    );
  }

  return null;
}
