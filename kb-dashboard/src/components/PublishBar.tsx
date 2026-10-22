"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchReindexStatus } from "@/lib/kb-client";
import type { ReindexStatusResponse, StatusTone } from "@/lib/kb-types";

type PanelStatus = {
  tone: StatusTone;
  message: string;
};

type StatusDetail = PanelStatus;

type LoadingDetail = {
  loading: boolean;
};

type DraftStateDetail = {
  hasFile: boolean;
  hasUnsavedChanges: boolean;
};

type PublishStartDetail = {
  path: string;
};

type PublishFinishDetail = {
  path: string;
  at: string;
};

type StoredPublishDetail = {
  path: string;
  at: string;
};

const EVENT_STATUS = "kb:status";
const EVENT_CATALOG_LOADING = "kb:catalog-loading";
const EVENT_FILE_LOADING = "kb:file-loading";
const EVENT_DRAFT_STATE = "kb:draft-state";
const EVENT_PUBLISH_START = "kb:publish-start";
const EVENT_PUBLISH_FINISH = "kb:publish-finish";
const EVENT_REFRESH_CATALOG = "kb:refresh-catalog";

const STORAGE_PUBLISH_KEY = "kb:last-publish";

const initialStatus: PanelStatus = {
  tone: "neutral",
  message: "Load a file to start editing the knowledge base.",
};

function statusClass(tone: StatusTone): string {
  if (tone === "success") {
    return "status-pill status-success";
  }
  if (tone === "error") {
    return "status-pill status-error";
  }
  return "status-pill status-neutral";
}

export default function PublishBar() {
  const [status, setStatus] = useState<PanelStatus>(initialStatus);
  const [reindexStatus, setReindexStatus] = useState<ReindexStatusResponse | null>(null);
  const [hasPublished, setHasPublished] = useState<boolean>(false);
  const [rebuildDismissed, setRebuildDismissed] = useState<boolean>(false);
  const [lastPublishedAt, setLastPublishedAt] = useState<string>("");
  const [lastPublishedFile, setLastPublishedFile] = useState<string>("");
  const [isCatalogLoading, setCatalogLoading] = useState<boolean>(false);
  const [isFileLoading, setFileLoading] = useState<boolean>(false);
  const [draftState, setDraftState] = useState<DraftStateDetail>({
    hasFile: false,
    hasUnsavedChanges: false,
  });

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const publishedAtLabel = useMemo(() => {
    if (!lastPublishedAt) {
      return "Not published yet";
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(lastPublishedAt));
  }, [lastPublishedAt]);

  const lastPublishedFileLabel = lastPublishedFile || "Not published yet";

  const rebuildStatusLabel = reindexStatus?.status ?? "idle";
  const rebuildMessage = reindexStatus?.message ?? "Idle";
  const showRebuildCard =
    hasPublished &&
    !rebuildDismissed &&
    (rebuildStatusLabel === "running" || rebuildStatusLabel === "completed");
  const rebuildStatusText = rebuildStatusLabel === "completed" ? "completed" : rebuildStatusLabel;
  const rebuildTone: StatusTone =
    rebuildStatusLabel === "running" || rebuildStatusLabel === "idle"
      ? "neutral"
      : rebuildStatusLabel === "failed"
        ? "error"
        : "success";

  const stopReindexPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const loadReindexStatus = useCallback(async () => {
    try {
      const statusData = await fetchReindexStatus();
      setReindexStatus(statusData);
      if (statusData.status !== "running") {
        stopReindexPolling();
      }
    } catch {
      setReindexStatus((current) =>
        current ?? {
          status: "idle",
          progress: 0,
          message: "Unable to fetch rebuild status",
        },
      );
    }
  }, [stopReindexPolling]);

  const startReindexPolling = useCallback(() => {
    if (pollingRef.current) {
      return;
    }
    pollingRef.current = setInterval(() => {
      void loadReindexStatus();
    }, 1500);
  }, [loadReindexStatus]);

  useEffect(() => {
    const task = window.setTimeout(() => {
      void loadReindexStatus();
    }, 0);
    return () => window.clearTimeout(task);
  }, [loadReindexStatus]);

  useEffect(() => {
    const task = window.setTimeout(() => {
      try {
        const stored = window.localStorage.getItem(STORAGE_PUBLISH_KEY);
        if (!stored) {
          return;
        }
        const parsed = JSON.parse(stored) as StoredPublishDetail;
        if (parsed?.at) {
          setLastPublishedAt(parsed.at);
        }
        if (parsed?.path) {
          setLastPublishedFile(parsed.path);
        }
        if (parsed?.at || parsed?.path) {
          setHasPublished(true);
        }
      } catch {
        window.localStorage.removeItem(STORAGE_PUBLISH_KEY);
      }
    }, 0);
    return () => window.clearTimeout(task);
  }, []);

  useEffect(() => () => stopReindexPolling(), [stopReindexPolling]);

  useEffect(() => {
    const statusHandler = (event: Event) => {
      const detail = (event as CustomEvent<StatusDetail>).detail;
      setStatus(detail);
    };
    const catalogHandler = (event: Event) => {
      const detail = (event as CustomEvent<LoadingDetail>).detail;
      setCatalogLoading(detail.loading);
    };
    const fileHandler = (event: Event) => {
      const detail = (event as CustomEvent<LoadingDetail>).detail;
      setFileLoading(detail.loading);
    };
    const draftHandler = (event: Event) => {
      const detail = (event as CustomEvent<DraftStateDetail>).detail;
      setDraftState(detail);
    };
    const publishStartHandler = (event: Event) => {
      const detail = (event as CustomEvent<PublishStartDetail>).detail;
      if (detail.path) {
        setHasPublished(true);
      }
      setRebuildDismissed(false);
      setReindexStatus({
        status: "running",
        progress: 0,
        message: "Rebuild running",
      });
      startReindexPolling();
    };
    const publishFinishHandler = (event: Event) => {
      const detail = (event as CustomEvent<PublishFinishDetail>).detail;
      setLastPublishedAt(detail.at);
      setLastPublishedFile(detail.path);
      try {
        const payload: StoredPublishDetail = { at: detail.at, path: detail.path };
        window.localStorage.setItem(STORAGE_PUBLISH_KEY, JSON.stringify(payload));
      } catch {
        window.localStorage.removeItem(STORAGE_PUBLISH_KEY);
      }
    };

    window.addEventListener(EVENT_STATUS, statusHandler);
    window.addEventListener(EVENT_CATALOG_LOADING, catalogHandler);
    window.addEventListener(EVENT_FILE_LOADING, fileHandler);
    window.addEventListener(EVENT_DRAFT_STATE, draftHandler);
    window.addEventListener(EVENT_PUBLISH_START, publishStartHandler);
    window.addEventListener(EVENT_PUBLISH_FINISH, publishFinishHandler);

    return () => {
      window.removeEventListener(EVENT_STATUS, statusHandler);
      window.removeEventListener(EVENT_CATALOG_LOADING, catalogHandler);
      window.removeEventListener(EVENT_FILE_LOADING, fileHandler);
      window.removeEventListener(EVENT_DRAFT_STATE, draftHandler);
      window.removeEventListener(EVENT_PUBLISH_START, publishStartHandler);
      window.removeEventListener(EVENT_PUBLISH_FINISH, publishFinishHandler);
    };
  }, [startReindexPolling]);

  return (
    <section className="panel rise-in p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="badge">Knowledge Console</span>
          <h1 className="mt-2 text-2xl font-semibold sm:text-3xl">Knowledge Base Editor</h1>
          <p className="mt-2 text-sm text-[#4f6666]">
            Save drafts, then publish to update the FAISS index.
          </p>
        </div>

        <div>
          <button
            type="button"
            onClick={() => {
              window.dispatchEvent(new CustomEvent(EVENT_REFRESH_CATALOG));
            }}
            disabled={isCatalogLoading || isFileLoading}
            className="rounded-lg border border-[#c9d8d8] bg-white px-3 py-2 text-sm text-[#355555] transition enabled:hover:bg-[#edf6f6] disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isCatalogLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <span className={statusClass(status.tone)}>{status.message}</span>
        {draftState.hasFile ? (
          <span className={statusClass(draftState.hasUnsavedChanges ? "error" : "success")}>
            {draftState.hasUnsavedChanges ? "Draft has unsaved changes" : "Draft saved"}
          </span>
        ) : null}
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-[#e6d9c9] bg-[#fffaf3] p-3">
          <p className="text-xs font-semibold tracking-[0.08em] text-[#7d5f4f] uppercase">
            Published At
          </p>
          <p className="mt-2 text-sm font-medium text-[#2f4e4e]">{publishedAtLabel}</p>
        </div>
        <div className="rounded-xl border border-[#e6d9c9] bg-[#fffaf3] p-3">
          <p className="text-xs font-semibold tracking-[0.08em] text-[#7d5f4f] uppercase">
            Last Published File
          </p>
          <p className="mt-2 wrap-break-word text-sm font-medium text-[#2f4e4e]">
            {lastPublishedFileLabel}
          </p>
        </div>
        {showRebuildCard ? (
          <div className="rounded-xl border border-[#e6d9c9] bg-[#fffaf3] p-3 sm:col-span-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold tracking-[0.08em] text-[#7d5f4f] uppercase">
                FAISS Rebuild Progress
              </p>
              <div className="flex items-center gap-2">
                <span className={statusClass(rebuildTone)}>{rebuildStatusText}</span>
                {rebuildStatusLabel === "completed" && (
                  <button
                    type="button"
                    onClick={() => setRebuildDismissed(true)}
                    aria-label="Dismiss rebuild status"
                    className="flex h-5 w-5 items-center justify-center rounded-full text-[#7d5f4f] transition hover:bg-[#f1e5d7]"
                  >
                    {"\u2715"}
                  </button>
                )}
              </div>
            </div>
            <p className="mt-2 text-xs text-[#5e6f6f]">{rebuildMessage}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
