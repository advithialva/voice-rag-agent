"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createKbFolder,
  createKbFile,
  deleteKbFile,
  fetchKbFile,
  fetchKbFiles,
} from "@/lib/kb-client";
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

const EVENT_STATUS = "kb:status";
const EVENT_OPEN_FILE = "kb:open-file";
const EVENT_FILE_LOADING = "kb:file-loading";
const EVENT_DRAFT_STATE = "kb:draft-state";
const EVENT_CATALOG_LOADING = "kb:catalog-loading";
const EVENT_REFRESH_CATALOG = "kb:refresh-catalog";
const EVENT_EDITOR_BUSY = "kb:editor-busy";

function emitEvent<T>(name: string, detail: T) {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

function emitStatus(message: string, tone: StatusTone = "neutral") {
  emitEvent<StatusDetail>(EVENT_STATUS, { message, tone });
}

function emitOpenFile(path: string, content: string) {
  emitEvent<OpenFileDetail>(EVENT_OPEN_FILE, { path, content });
}

function emitLoading(name: string, loading: boolean) {
  emitEvent<LoadingDetail>(name, { loading });
}

export default function FileTree() {
  const [files, setFiles] = useState<string[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [selectedFolder, setSelectedFolder] = useState<string>("");
  const [newFolderInput, setNewFolderInput] = useState<string>("");
  const [newFileName, setNewFileName] = useState<string>("");
  const [isCreatingFolder, setCreatingFolder] = useState<boolean>(false);
  const [isCreatingFile, setCreatingFile] = useState<boolean>(false);
  const [isDeletingFile, setDeletingFile] = useState<boolean>(false);
  const [isEditorSaving, setEditorSaving] = useState<boolean>(false);
  const [isEditorPublishing, setEditorPublishing] = useState<boolean>(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);

  const filteredFiles = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return files;
    }
    return files.filter((filePath) => filePath.toLowerCase().includes(query));
  }, [files, search]);

  const visibleFolders = useMemo(
    () => folders.filter((folder) => folder !== "."),
    [folders],
  );

  const openFile = useCallback(async (path: string) => {
    emitLoading(EVENT_FILE_LOADING, true);
    try {
      const data = await fetchKbFile(path);
      setSelectedPath(data.path);
      emitOpenFile(data.path, data.content);
      emitStatus(`Opened ${data.path}`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to load file.";
      emitStatus(message, "error");
    } finally {
      emitLoading(EVENT_FILE_LOADING, false);
    }
  }, []);

  const loadCatalog = useCallback(
    async (preferredFile?: string) => {
      emitLoading(EVENT_CATALOG_LOADING, true);
      try {
        const data = await fetchKbFiles();
        setFiles(data.files);
        setFolders(data.folders);

        const nextFolder =
          (data.folders.find((folder) => folder !== ".") ?? data.folders[0]) ?? "";
        if ((!selectedFolder || !data.folders.includes(selectedFolder)) && nextFolder) {
          setSelectedFolder(nextFolder);
        }

        const currentOrPreferred =
          preferredFile && data.files.includes(preferredFile)
            ? preferredFile
            : selectedPath && data.files.includes(selectedPath)
              ? selectedPath
              : data.files[0] ?? "";

        if (!currentOrPreferred) {
          setSelectedPath("");
          emitOpenFile("", "");
          emitStatus("No editable knowledge files found yet.", "neutral");
          return;
        }

        await openFile(currentOrPreferred);
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load catalog. Verify backend service is running.";
        emitStatus(message, "error");
      } finally {
        emitLoading(EVENT_CATALOG_LOADING, false);
      }
    },
    [openFile, selectedFolder, selectedPath],
  );

  useEffect(() => {
    const task = window.setTimeout(() => {
      void loadCatalog();
    }, 0);
    return () => window.clearTimeout(task);
  }, [loadCatalog]);

  useEffect(() => {
    const handler = () => {
      void loadCatalog();
    };
    window.addEventListener(EVENT_REFRESH_CATALOG, handler);
    return () => window.removeEventListener(EVENT_REFRESH_CATALOG, handler);
  }, [loadCatalog]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<EditorBusyDetail>).detail;
      setEditorSaving(detail.saving);
      setEditorPublishing(detail.publishing);
    };
    window.addEventListener(EVENT_EDITOR_BUSY, handler);
    return () => window.removeEventListener(EVENT_EDITOR_BUSY, handler);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<DraftStateDetail>).detail;
      setHasUnsavedChanges(detail.hasUnsavedChanges);
    };
    window.addEventListener(EVENT_DRAFT_STATE, handler);
    return () => window.removeEventListener(EVENT_DRAFT_STATE, handler);
  }, []);

  async function handleCreate() {
    const trimmedName = newFileName.trim();
    const trimmedFolder = newFolderInput.trim().replace(/\/+$/, "");
    const targetFolder = trimmedFolder || selectedFolder.trim();
    if (!trimmedFolder) {
      if (!targetFolder) {
        emitStatus("Choose or enter a folder path for the new file.", "error");
        return;
      }
    }
    if (!trimmedName) {
      emitStatus("Enter a file name.", "error");
      return;
    }

    setCreatingFile(true);
    try {
      const created = await createKbFile({
        folder: targetFolder,
        file_name: trimmedName,
        content: "",
      });
      setNewFileName("");
      setNewFolderInput("");
      setSelectedFolder(targetFolder);
      await loadCatalog(created.path);
      emitStatus(created.message || `Created ${created.path}`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "File creation failed.";
      emitStatus(message, "error");
    } finally {
      setCreatingFile(false);
    }
  }

  async function handleCreateFolder() {
    const trimmed = newFolderInput.trim().replace(/\/+$/, "");
    if (!trimmed) {
      emitStatus("Enter a folder path to create.", "error");
      return;
    }

    setCreatingFolder(true);
    try {
      const result = await createKbFolder({ folder: trimmed });
      setSelectedFolder(result.path || trimmed);
      setNewFolderInput("");
      await loadCatalog();
      emitStatus(result.message || `Created folder ${result.path}`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Folder creation failed.";
      emitStatus(message, "error");
    } finally {
      setCreatingFolder(false);
    }
  }

  async function handleDelete() {
    if (!selectedPath) {
      emitStatus("Select a file before deleting.", "error");
      return;
    }

    const warning = hasUnsavedChanges
      ? `Delete ${selectedPath}? You have unsaved changes that will be lost. This cannot be undone.`
      : `Delete ${selectedPath}? This cannot be undone.`;

    if (!window.confirm(warning)) {
      return;
    }

    setDeletingFile(true);
    try {
      const result = await deleteKbFile(selectedPath);
      setSelectedPath("");
      emitOpenFile("", "");
      await loadCatalog();
      emitStatus(result.message || `Deleted ${result.path}`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Delete failed.";
      emitStatus(message, "error");
    } finally {
      setDeletingFile(false);
    }
  }

  return (
    <aside className="panel rise-in p-5" style={{ animationDelay: "90ms" }}>
      <div className="space-y-4">
        <div className="space-y-2">
          <label
            className="text-xs font-semibold tracking-widest text-[#775b4a] uppercase"
            htmlFor="search-file"
          >
            Search files
          </label>
          <input
            id="search-file"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter paths..."
            className="w-full rounded-lg border border-[#d8cab8] bg-[#fffdf9] px-3 py-2 text-sm outline-none focus:border-[#f09477]"
          />
        </div>

        <div className="max-h-90 space-y-2 overflow-auto pr-1">
          {filteredFiles.length === 0 ? (
            <p className="text-sm text-[#6f7e7e]">No files matched your search.</p>
          ) : (
            filteredFiles.map((filePath) => {
              const isActive = filePath === selectedPath;
              return (
                <button
                  key={filePath}
                  type="button"
                  onClick={() => {
                    void openFile(filePath);
                  }}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-xs leading-5 transition ${
                    isActive
                      ? "border-[#f2a181] bg-[#ffe8dd] text-[#733f31]"
                      : "border-[#dfd5c8] bg-white text-[#495e5e] hover:bg-[#f8f5ef]"
                  }`}
                >
                  {filePath}
                </button>
              );
            })
          )}
        </div>

        <div className="space-y-2 border-t border-[#e8dccf] pt-4">
          <p className="text-xs font-semibold tracking-widest text-[#775b4a] uppercase">
            Delete selected file
          </p>
          <p className="text-xs text-[#6f7e7e]">
            Selected: {selectedPath || "None"}
          </p>
          <button
            type="button"
            onClick={() => {
              void handleDelete();
            }}
            disabled={
              !selectedPath ||
              isDeletingFile ||
              isEditorSaving ||
              isEditorPublishing ||
              isCreatingFile ||
              isCreatingFolder
            }
            className="w-full rounded-lg border border-[#f0c4b6] bg-[#fff1ec] px-3 py-2 text-sm font-medium text-[#8a3b2e] transition enabled:hover:bg-[#ffe4db] disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isDeletingFile ? "Deleting..." : "Delete File"}
          </button>
        </div>

        <div className="space-y-3 border-t border-[#e8dccf] pt-4">
          <p className="text-xs font-semibold tracking-widest text-[#775b4a] uppercase">
            Create new file
          </p>
          <div className="space-y-2">
            <label className="text-xs font-medium text-[#5a6a6a]">Existing folders</label>
            <select
              value={selectedFolder}
              onChange={(event) => setSelectedFolder(event.target.value)}
              className="w-full rounded-lg border border-[#d8cab8] bg-[#fffdf9] px-3 py-2 text-sm outline-none"
            >
              {visibleFolders.map((folder) => (
                <option key={folder} value={folder}>
                  {folder}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-[#5a6a6a]">Create new folder</label>
            <div className="flex items-center gap-2">
              <input
                value={newFolderInput}
                onChange={(event) => setNewFolderInput(event.target.value)}
                placeholder="Products/Industrial IO"
                className="flex-1 rounded-lg border border-[#d8cab8] bg-[#fffdf9] px-3 py-2 text-sm outline-none focus:border-[#f09477]"
              />
              <button
                type="button"
                onClick={() => {
                  void handleCreateFolder();
                }}
                disabled={isCreatingFolder}
                className="rounded-lg border border-[#d2d8e0] bg-white px-3 py-2 text-xs font-semibold text-[#335353] transition enabled:hover:bg-[#edf6f6] disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isCreatingFolder ? "Creating..." : "Create Folder"}
              </button>
            </div>
          </div>
          <input
            value={newFileName}
            onChange={(event) => setNewFileName(event.target.value)}
            placeholder="new-file.txt"
            className="w-full rounded-lg border border-[#d8cab8] bg-[#fffdf9] px-3 py-2 text-sm outline-none focus:border-[#f09477]"
          />
          <button
            type="button"
            onClick={() => {
              void handleCreate();
            }}
            disabled={isCreatingFile || isEditorSaving || isEditorPublishing || isCreatingFolder}
            className="w-full rounded-lg border border-[#d4d9cb] bg-[#eef7ea] px-3 py-2 text-sm font-medium text-[#2f5d39] transition enabled:hover:bg-[#dff0d7] disabled:cursor-not-allowed disabled:opacity-70"
          >
            Create File
          </button>
        </div>
      </div>
    </aside>
  );
}
