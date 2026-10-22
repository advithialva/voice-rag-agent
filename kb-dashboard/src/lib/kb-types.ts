export type StatusTone = "neutral" | "success" | "error";

export interface FilesResponse {
  files: string[];
  folders: string[];
}

export interface FileResponse {
  path: string;
  content: string;
}

export interface SavePayload {
  path: string;
  content: string;
}

export interface SaveResponse {
  ok: boolean;
  path: string;
  message: string;
}

export interface CreatePayload {
  folder: string;
  file_name: string;
  content: string;
}

export interface CreateResponse {
  ok: boolean;
  path: string;
  message: string;
}

export interface CreateFolderPayload {
  folder: string;
}

export interface CreateFolderResponse {
  ok: boolean;
  path: string;
  message: string;
}

export interface DeleteResponse {
  ok: boolean;
  path: string;
  message: string;
}

export interface ReindexResponse {
  ok: boolean;
  message: string;
  output?: string;
}

export interface PublishResponse {
  ok: boolean;
  path: string;
  message: string;
  save_message?: string;
  output?: string;
  returncode?: number;
}

export type ReindexStatusState = "idle" | "running" | "completed" | "failed";

export interface ReindexStatusResponse {
  status: ReindexStatusState;
  progress: number;
  message?: string;
  started_at?: string;
  finished_at?: string;
  output_tail?: string;
}

export interface ApiErrorShape {
  message?: string;
  detail?: string;
}