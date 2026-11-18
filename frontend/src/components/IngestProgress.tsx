import { useEffect, useState } from "react";
import type { IngestProgressData, IngestProgressStageStep } from "../types/api";

interface IngestProgressProps {
  token: string;
  onIngestCompleted?: () => void;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let val = bytes;
  let unitIndex = 0;
  while (val >= 1024 && unitIndex < units.length - 1) {
    val /= 1024;
    unitIndex++;
  }
  return `${val.toFixed(val >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
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
          const nextInterval = data.is_running ? 1000 : 8000;
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
    const detail = progress.current_detail;
    const currentDataset = progress.current_dataset;
    const stageSteps: IngestProgressStageStep[] = progress.stage_steps || [];

    return (
      <section className="mb-4 flex flex-col gap-4 border border-amber-500/50 bg-panel p-4 shadow-flat">
        {/* Top Header: Overall Status & Timer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-amber-500" />
            </span>
            <h2 className="text-sm font-semibold tracking-wide text-zinc-100">
              Database Ingestion Active
            </h2>
            <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-300">
              {progress.completed_count} / {progress.total_count} datasets (
              {progress.percent}%)
            </span>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs text-zinc-300">
            <span className="text-zinc-500">Total Elapsed:</span>
            <span className="font-semibold text-amber-400">
              {formatDuration(progress.elapsed_seconds)}
            </span>
          </div>
        </div>

        {/* Overall Datasets Progress Bar */}
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs text-zinc-400">
            <span>Overall Datasets Progress</span>
            <span className="font-mono text-zinc-200">{progress.percent}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full bg-gradient-to-r from-amber-600 via-amber-500 to-amber-300 transition-all duration-300"
              style={{ width: `${Math.max(progress.percent, 3)}%` }}
            />
          </div>
        </div>

        {/* Active Dataset Granular Card */}
        {currentDataset ? (
          <div className="rounded border border-zinc-800 bg-zinc-900/70 p-3.5 shadow-inner">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-amber-400">
                  Processing:
                </span>
                <span className="font-mono text-sm font-semibold text-zinc-100">
                  {currentDataset}
                </span>
              </div>

              {detail && detail.speed_mb_s > 0 ? (
                <div className="flex items-center gap-3 text-xs">
                  <span className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-300">
                    ⚡ {detail.speed_mb_s} MB/s
                  </span>
                  {detail.eta_seconds ? (
                    <span className="text-zinc-400">
                      ETA:{" "}
                      <strong className="text-zinc-200">
                        {formatDuration(detail.eta_seconds)}
                      </strong>
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>

            {/* Stepper of stages for the current dataset */}
            <div className="my-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {stageSteps.map((step, idx) => {
                const isCurrent = step.status === "running";
                const isDone = step.status === "completed";

                return (
                  <div
                    key={step.id}
                    className={`flex items-center gap-2 rounded border px-3 py-2 text-xs transition ${
                      isCurrent
                        ? "border-amber-500 bg-amber-500/10 text-amber-200 shadow-sm"
                        : isDone
                          ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-300"
                          : "border-zinc-800 bg-zinc-950/40 text-zinc-500"
                    }`}
                  >
                    <div
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                        isCurrent
                          ? "bg-amber-500 text-zinc-950 font-extrabold animate-pulse"
                          : isDone
                            ? "bg-emerald-500 text-zinc-950 font-extrabold"
                            : "bg-zinc-800 text-zinc-400"
                      }`}
                    >
                      {isDone ? "✓" : idx + 1}
                    </div>

                    <div className="flex min-w-0 flex-col">
                      <span className="truncate font-medium">{step.label}</span>
                      {isCurrent && step.percent > 0 ? (
                        <span className="text-[10px] font-mono text-amber-300">
                          {step.percent}%
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Granular Byte / Stage Progress Bar */}
            {detail && detail.bytes_total > 0 ? (
              <div className="flex flex-col gap-1.5 pt-1">
                <div className="flex justify-between text-xs text-zinc-300">
                  <span className="text-zinc-400 truncate pr-2">
                    {detail.detail}
                  </span>
                  <span className="shrink-0 font-mono text-amber-300 font-semibold">
                    {detail.percent}% ({formatBytes(detail.bytes_current)} /{" "}
                    {formatBytes(detail.bytes_total)})
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-300 transition-all duration-200"
                    style={{ width: `${Math.max(detail.percent, 2)}%` }}
                  />
                </div>
                {detail.uncompressed_bytes > 0 ? (
                  <div className="text-right text-[10px] text-zinc-500">
                    Streamed uncompressed raw data:{" "}
                    {formatBytes(detail.uncompressed_bytes)}
                  </div>
                ) : null}
              </div>
            ) : detail ? (
              <div className="flex items-center gap-2 pt-1 text-xs text-zinc-400">
                <svg
                  className="h-3.5 w-3.5 animate-spin text-amber-400"
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
                <span>{detail.detail}</span>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Datasets Session Queue List */}
        <div className="flex flex-col gap-2 pt-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
            Session Datasets Queue:
          </span>
          <div className="flex flex-wrap gap-2">
            {progress.items.map((item) => {
              const isRunning =
                item.status !== "queued" &&
                item.status !== "completed" &&
                item.status !== "failed";
              const isCompleted = item.status === "completed";
              const isFailed = item.status === "failed";

              return (
                <div
                  key={item.name}
                  className={`flex items-center gap-2 rounded border px-3 py-1.5 text-xs transition ${
                    isRunning
                      ? "border-amber-500/70 bg-amber-500/10 text-amber-200 font-medium"
                      : isCompleted
                        ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
                        : isFailed
                          ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                          : "border-zinc-800 bg-zinc-950/60 text-zinc-400"
                  }`}
                >
                  {isRunning ? (
                    <svg
                      className="h-3.5 w-3.5 animate-spin text-amber-400"
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
                    <span className="font-bold text-emerald-400">✓</span>
                  ) : isFailed ? (
                    <span className="font-bold text-rose-400">✕</span>
                  ) : (
                    <span className="text-zinc-600">○</span>
                  )}
                  <span className="font-mono">{item.name}</span>
                  {item.duration ? (
                    <span className="rounded bg-zinc-800 px-1.5 py-0.2 font-mono text-[10px] text-zinc-300">
                      {formatDuration(item.duration)}
                    </span>
                  ) : isRunning ? (
                    <span className="text-[10px] text-amber-300/80 uppercase tracking-wider font-semibold">
                      [{item.status}]
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
            <strong className="text-emerald-200">
              {formatDuration(lastFinishedDuration)}
            </strong>
            .
          </span>
        </div>
        <button
          type="button"
          onClick={() => setShowFinishedBanner(false)}
          className="text-emerald-400 hover:text-emerald-200 text-sm font-bold px-2 py-0.5"
        >
          ✕
        </button>
      </section>
    );
  }

  return null;
}
