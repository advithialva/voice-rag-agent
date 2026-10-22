import type {
  ApiErrorShape,
  CreateFolderPayload,
  CreateFolderResponse,
  CreatePayload,
  CreateResponse,
  DeleteResponse,
  FileResponse,
  FilesResponse,
  PublishResponse,
  ReindexResponse,
  ReindexStatusResponse,
  SavePayload,
  SaveResponse,
} from "@/lib/kb-types";

const API_BASE = "/api/kb";

async function parseJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T | ApiErrorShape;
  if (!response.ok) {
    const errorShape = payload as ApiErrorShape;
    throw new Error(errorShape.message ?? errorShape.detail ?? "Request failed.");
  }
  return payload as T;
}

export async function fetchKbFiles(): Promise<FilesResponse> {
  const response = await fetch(`${API_BASE}/files`, { cache: "no-store" });
  return parseJson<FilesResponse>(response);
}

export async function fetchKbFile(path: string): Promise<FileResponse> {
  const response = await fetch(`${API_BASE}/file?path=${encodeURIComponent(path)}`, {
    cache: "no-store",
  });
  return parseJson<FileResponse>(response);
}

export async function deleteKbFile(path: string): Promise<DeleteResponse> {
  const response = await fetch(`${API_BASE}/file?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  });
  return parseJson<DeleteResponse>(response);
}

export async function saveKbFile(payload: SavePayload): Promise<SaveResponse> {
  const response = await fetch(`${API_BASE}/save`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson<SaveResponse>(response);
}

export async function createKbFile(payload: CreatePayload): Promise<CreateResponse> {
  const response = await fetch(`${API_BASE}/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson<CreateResponse>(response);
}

export async function createKbFolder(payload: CreateFolderPayload): Promise<CreateFolderResponse> {
  const response = await fetch(`${API_BASE}/folder`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson<CreateFolderResponse>(response);
}

export async function reindexKb(): Promise<ReindexResponse> {
  const response = await fetch(`${API_BASE}/reindex`, {
    method: "POST",
  });
  return parseJson<ReindexResponse>(response);
}

export async function publishKbFile(payload: SavePayload): Promise<PublishResponse> {
  const response = await fetch(`${API_BASE}/publish`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson<PublishResponse>(response);
}

export async function fetchReindexStatus(): Promise<ReindexStatusResponse> {
  const response = await fetch(`${API_BASE}/reindex/status`, {
    cache: "no-store",
  });
  return parseJson<ReindexStatusResponse>(response);
}