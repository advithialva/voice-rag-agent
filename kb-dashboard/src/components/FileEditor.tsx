"use client";

import { useEffect, useMemo, useState } from "react";

import { publishKbFile, saveKbFile } from "@/lib/kb-client";
import type { StatusTone } from "@/lib/kb-types";

type StatusDetail = {
  message: string;
  tone: StatusTone;
};

type OpenFileDetail = {
  path: string;
  content: string;
};

type LoadingDetail = {
  loading: boolean;
};

type DraftStateDetail = {
  hasFile: boolean;
  hasUnsavedChanges: boolean;
};

type EditorBusyDetail = {
  saving: boolean;
  publishing: boolean;
};

type PublishStartDetail = {
  path: string;
};

type PublishFinishDetail = {
  path: string;
  at: string;
};

const EVENT_STATUS = "kb:status";
const EVENT_OPEN_FILE = "kb:open-file";
const EVENT_FILE_LOADING = "kb:file-loading";
const EVENT_DRAFT_STATE = "kb:draft-state";
const EVENT_EDITOR_BUSY = "kb:editor-busy";
const EVENT_PUBLISH_START = "kb:publish-start";
const EVENT_PUBLISH_FINISH = "kb:publish-finish";

function emitEvent<T>(name: string, detail: T) {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

function emitStatus(message: string, tone: StatusTone = "neutral") {
  emitEvent<StatusDetail>(EVENT_STATUS, { message, tone });
}

export default function FileEditor() {
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [lastSavedContent, setLastSavedContent] = useState<string>("");
  const [publishOutput, setPublishOutput] = useState<string>("");
  const [isSaving, setSaving] = useState<boolean>(false);
  const [isPublishing, setPublishing] = useState<boolean>(false);
  const [isFileLoading, setFileLoading] = useState<boolean>(false);

  const hasUnsavedChanges = useMemo(
    () => selectedPath.length > 0 && content !== lastSavedContent,
    [content, lastSavedContent, selectedPath],
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<OpenFileDetail>).detail;
      setSelectedPath(detail.path || "");
      setContent(detail.content || "");
      setLastSavedContent(detail.content || "");
      setPublishOutput("");
    };
    window.addEventListener(EVENT_OPEN_FILE, handler);
    return () => window.removeEventListener(EVENT_OPEN_FILE, handler);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<LoadingDetail>).detail;
      setFileLoading(detail.loading);
    };
    window.addEventListener(EVENT_FILE_LOADING, handler);
    return () => window.removeEventListener(EVENT_FILE_LOADING, handler);
  }, []);

  useEffect(() => {
    emitEvent<DraftStateDetail>(EVENT_DRAFT_STATE, {
      hasFile: Boolean(selectedPath),
      hasUnsavedChanges,
    });
  }, [hasUnsavedChanges, selectedPath]);

  useEffect(() => {
    emitEvent<EditorBusyDetail>(EVENT_EDITOR_BUSY, {
      saving: isSaving,
      publishing: isPublishing,
    });
  }, [isPublishing, isSaving]);

  async function handleSave(): Promise<boolean> {
    if (!selectedPath) {
      emitStatus("Select a file before saving.", "error");
      return false;
    }

    setSaving(true);
    try {
      const result = await saveKbFile({
        path: selectedPath,
        content,
      });
      setLastSavedContent(content);
      emitStatus(result.message || `Draft saved for ${selectedPath}`, "success");
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Save failed.";
      emitStatus(message, "error");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish() {
    if (!selectedPath) {
      emitStatus("Select a file before publishing.", "error");
      return;
    }

    if (hasUnsavedChanges) {
      emitStatus("Save draft before publishing.", "error");
      return;
    }

    setPublishing(true);
    setPublishOutput("");
    emitEvent<PublishStartDetail>(EVENT_PUBLISH_START, { path: selectedPath });
    emitStatus(
      "Publishing draft and rebuilding FAISS index. This can take a few minutes.",
      "neutral",
    );

    try {
      const result = await publishKbFile({
        path: selectedPath,
        content,
      });

      setLastSavedContent(content);
      setPublishOutput(result.output ?? "No output returned.");
      emitEvent<PublishFinishDetail>(EVENT_PUBLISH_FINISH, {
        path: selectedPath,
        at: new Date().toISOString(),
      });
      emitStatus(result.message || "Publish completed.", result.ok ? "success" : "error");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Publish failed.";
      emitStatus(message, "error");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <section className="panel rise-in p-5" style={{ animationDelay: "140ms" }}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs tracking-[0.08em] text-[#7d5f4f] uppercase">Current file</p>
          <p className="font-mono text-sm text-[#335353]">
            {selectedPath || "No file selected"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void handleSave();
            }}
            disabled={isSaving || isPublishing || isFileLoading || !selectedPath}
            className="rounded-lg border border-[#d5dccc] bg-white px-3 py-2 text-sm font-medium text-[#3a5e40] transition enabled:hover:bg-[#eef7ea] disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSaving ? "Saving..." : "Save Draft"}
          </button>

          <button
            type="button"
            onClick={() => {
              void handlePublish();
            }}
            disabled={
              isSaving ||
              isPublishing ||
              isFileLoading ||
              !selectedPath ||
              hasUnsavedChanges
            }
            className="rounded-lg bg-(--sunrise) px-3 py-2 text-sm font-semibold text-white transition enabled:hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isPublishing ? "Publishing..." : "Publish"}
          </button>
        </div>
      </div>

      <textarea
        value={content}
        onChange={(event) => {
          setContent(event.target.value);
        }}
        disabled={!selectedPath || isFileLoading}
        className="mt-3 min-h-90 w-full rounded-xl border border-[#ddd2c4] bg-[#fffefb] p-4 font-mono text-sm leading-6 text-[#294545] outline-none focus:border-[#f0a588] disabled:cursor-not-allowed disabled:bg-[#f4f0e9]"
        placeholder={isFileLoading ? "Loading file..." : "Select a file from the left panel."}
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-start">
        <div className="rounded-xl border border-[#e6d9c9] bg-[#fff8f0] p-3">
          <p className="text-xs font-semibold tracking-[0.08em] text-[#7d5f4f] uppercase">
            Publish output
          </p>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-5 text-[#4f5f5f]">
            {publishOutput || "Run Publish to view backend output here."}
          </pre>
        </div>
        <p className="text-xs leading-5 text-[#617878]">
          Keep filenames and folder structure stable so retrieval metadata remains consistent.
        </p>
      </div>
    </section>
  );
}
