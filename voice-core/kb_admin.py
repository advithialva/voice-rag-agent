import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
KB_ROOT = (BASE_DIR / "knowledge_base").resolve()
BACKUP_ROOT = (BASE_DIR / "KMS" / "kb_history").resolve()
VALID_FILE_NAME = re.compile(r"^[A-Za-z0-9._ -]+\.txt$")

app = FastAPI(title="Knowledge Base Admin API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_reindex_lock = asyncio.Lock()
_progress_pattern = re.compile(r"(\d{1,3})%\|")
_progress_marker = re.compile(r"PROGRESS:\s*(\d{1,3})")

_reindex_state: dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "message": "Idle",
    "started_at": None,
    "finished_at": None,
    "output_tail": "",
}


class SavePayload(BaseModel):
    path: str
    content: str


class CreatePayload(BaseModel):
    folder: str
    file_name: str
    content: str = ""


class CreateFolderPayload(BaseModel):
    folder: str


def _save_file_content(path: str, content: str) -> dict[str, Any]:
    file_path = _validate_relative_file_path(path)
    backup_path = _backup_file_if_exists(file_path)
    file_path.write_text(content, encoding="utf-8")

    relative_path = file_path.relative_to(KB_ROOT).as_posix()
    message = f"Saved {relative_path}."
    if backup_path:
        message += f" Backup stored at {backup_path}."

    return {
        "ok": True,
        "path": relative_path,
        "message": message,
    }


def _delete_file(path: str) -> dict[str, Any]:
    file_path = _validate_relative_file_path(path)
    backup_path = _backup_file_if_exists(file_path)
    try:
        file_path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to delete file.") from exc

    relative_path = file_path.relative_to(KB_ROOT).as_posix()
    message = f"Deleted {relative_path}."
    if backup_path:
        message += f" Backup stored at {backup_path}."

    return {
        "ok": True,
        "path": relative_path,
        "message": message,
    }


def _is_inside(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _normalize_relative_path(path: str) -> Path:
    clean = (path or "").strip().replace("\\", "/")
    if not clean:
        raise HTTPException(status_code=400, detail="Path is required.")
    if clean.startswith("/"):
        raise HTTPException(status_code=400, detail="Path must be relative.")
    if ".." in clean.split("/"):
        raise HTTPException(status_code=400, detail="Path traversal is not allowed.")
    return Path(clean)


def _validate_relative_file_path(path: str) -> Path:
    rel = _normalize_relative_path(path)
    if rel.suffix.lower() != ".txt":
        raise HTTPException(status_code=400, detail="Only .txt files can be edited.")

    abs_path = (KB_ROOT / rel).resolve()
    if not _is_inside(KB_ROOT, abs_path):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return abs_path


def _resolve_folder_path_for_create(folder: str) -> Path:
    clean = (folder or ".").strip()
    rel = _normalize_relative_path(clean)
    abs_path = (KB_ROOT / rel).resolve()
    if not _is_inside(KB_ROOT, abs_path):
        raise HTTPException(status_code=400, detail="Invalid folder path.")

    return abs_path


def _validate_file_name(file_name: str) -> str:
    clean = (file_name or "").strip()
    if not VALID_FILE_NAME.match(clean):
        raise HTTPException(
            status_code=400,
            detail="File name must end with .txt and contain only letters, numbers, spaces, dot, dash, or underscore.",
        )
    return clean


def _list_editable_files() -> list[str]:
    if not KB_ROOT.exists():
        return []

    files: list[str] = []
    for path in KB_ROOT.rglob("*.txt"):
        if not path.is_file():
            continue
        rel = path.relative_to(KB_ROOT)
        if rel.parts and rel.parts[0] in {"faiss_index", "_history"}:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        files.append(rel.as_posix())

    return sorted(files)


def _list_target_folders() -> list[str]:
    folders: set[str] = {"."}
    if not KB_ROOT.exists():
        return sorted(folders)

    for path in KB_ROOT.rglob("*"):
        if not path.is_dir():
            continue
        rel = path.relative_to(KB_ROOT)
        if not rel.parts:
            continue
        if rel.parts[0] in {"faiss_index", "_history"}:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        folders.add(rel.as_posix())

    return sorted(folders)


def _backup_file_if_exists(file_path: Path) -> str | None:
    if not file_path.exists():
        return None

    rel = file_path.relative_to(KB_ROOT)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp_folder = BACKUP_ROOT / file_path.stat().st_mtime_ns.__str__()
    target = (timestamp_folder / rel).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(file_path.read_bytes())
    return target.relative_to(BASE_DIR).as_posix()


def _run_ingestion_sync() -> dict[str, Any]:
    preferred_python = os.getenv("KB_ADMIN_PYTHON")
    if preferred_python:
        python_executable = Path(preferred_python)
    else:
        venv_python = BASE_DIR / "venv" / "bin" / "python"
        python_executable = venv_python if venv_python.exists() else Path(sys.executable)

    command = [python_executable.as_posix(), str(BASE_DIR / "data_ingestion.py")]
    started_at = datetime.now(timezone.utc).isoformat()

    _reindex_state.update(
        {
            "status": "running",
            "progress": 0,
            "message": "Reindex running",
            "started_at": started_at,
            "finished_at": None,
            "output_tail": "",
        }
    )

    output_lines: list[str] = []
    output_tail = ""

    with subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as process:
        if process.stdout:
            for line in process.stdout:
                output_lines.append(line)
                output_tail = (output_tail + line)[-4000:]
                marker = _progress_marker.search(line)
                if marker:
                    progress = min(99, int(marker.group(1)))
                    _reindex_state.update({"progress": progress})
                else:
                    match = _progress_pattern.search(line)
                    if match:
                        progress = min(99, int(match.group(1)))
                        _reindex_state.update({"progress": progress})
                    elif "FAISS index saved" in line:
                        _reindex_state.update({"progress": max(95, _reindex_state.get("progress", 0))})
                _reindex_state.update({"output_tail": output_tail})

        process.wait(timeout=900)

        ok = process.returncode == 0
        finished_at = datetime.now(timezone.utc).isoformat()
        _reindex_state.update(
            {
                "status": "completed" if ok else "failed",
                "progress": 100 if ok else _reindex_state.get("progress", 0),
                "message": "Reindex completed successfully." if ok else "Reindex failed.",
                "finished_at": finished_at,
                "output_tail": output_tail,
            }
        )

    combined_output = "".join(output_lines).strip()
    return {
        "ok": ok,
        "message": _reindex_state["message"],
        "output": combined_output,
        "returncode": process.returncode,
    }


async def _run_ingestion() -> dict[str, Any]:
    return await asyncio.to_thread(_run_ingestion_sync)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "knowledge_base_path": KB_ROOT.as_posix(),
        "editable_files_count": len(_list_editable_files()),
    }


@app.get("/api/reindex/status")
async def reindex_status() -> dict[str, Any]:
    return {
        "status": _reindex_state.get("status", "idle"),
        "progress": _reindex_state.get("progress", 0),
        "message": _reindex_state.get("message"),
        "started_at": _reindex_state.get("started_at"),
        "finished_at": _reindex_state.get("finished_at"),
        "output_tail": _reindex_state.get("output_tail"),
    }


@app.get("/api/files")
async def get_files() -> dict[str, Any]:
    if not KB_ROOT.exists():
        raise HTTPException(status_code=500, detail="knowledge_base folder not found.")

    return {
        "files": _list_editable_files(),
        "folders": _list_target_folders(),
    }


@app.get("/api/file")
async def get_file(path: str = Query(..., description="Relative file path inside knowledge_base")) -> dict[str, str]:
    file_path = _validate_relative_file_path(path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File is not UTF-8 encoded.") from exc

    return {
        "path": file_path.relative_to(KB_ROOT).as_posix(),
        "content": content,
    }


@app.delete("/api/file")
async def delete_file(
    path: str = Query(..., description="Relative file path inside knowledge_base"),
) -> dict[str, Any]:
    return _delete_file(path)


@app.post("/api/save")
async def save_file(payload: SavePayload) -> dict[str, Any]:
    return _save_file_content(payload.path, payload.content)


@app.post("/api/create")
async def create_file(payload: CreatePayload) -> dict[str, Any]:
    folder_path = _resolve_folder_path_for_create(payload.folder)
    file_name = _validate_file_name(payload.file_name)

    target_path = (folder_path / file_name).resolve()
    if not _is_inside(KB_ROOT, target_path):
        raise HTTPException(status_code=400, detail="Invalid destination path.")

    if target_path.exists():
        raise HTTPException(status_code=409, detail="File already exists.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(payload.content, encoding="utf-8")

    relative_path = target_path.relative_to(KB_ROOT).as_posix()
    return {
        "ok": True,
        "path": relative_path,
        "message": f"Created {relative_path}.",
    }


@app.post("/api/folder")
async def create_folder(payload: CreateFolderPayload) -> dict[str, Any]:
    folder_path = _resolve_folder_path_for_create(payload.folder)
    folder_path.mkdir(parents=True, exist_ok=True)

    relative_path = folder_path.relative_to(KB_ROOT).as_posix()
    return {
        "ok": True,
        "path": relative_path,
        "message": f"Created folder {relative_path}.",
    }


@app.post("/api/reindex")
async def reindex() -> dict[str, Any]:
    if _reindex_lock.locked():
        raise HTTPException(status_code=409, detail="Reindex already running. Please wait.")

    async with _reindex_lock:
        return await _run_ingestion()


@app.post("/api/publish")
async def publish(payload: SavePayload) -> dict[str, Any]:
    if _reindex_lock.locked():
        raise HTTPException(status_code=409, detail="Publish already running. Please wait.")

    async with _reindex_lock:
        save_result = _save_file_content(payload.path, payload.content)
        reindex_result = await _run_ingestion()

        message = (
            f"Published {save_result['path']} and updated FAISS index."
            if reindex_result["ok"]
            else f"Draft saved for {save_result['path']}, but publish failed while updating FAISS index."
        )

        return {
            **reindex_result,
            "path": save_result["path"],
            "save_message": save_result["message"],
            "message": message,
        }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8090)