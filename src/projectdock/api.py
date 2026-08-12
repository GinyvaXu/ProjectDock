from __future__ import annotations

import asyncio
import json
import os
import queue as queue_module
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import builder, presets, scanner, versioning
from .agent import AGENTS, build_command, system_prompt
from .config import APP_NAME, APP_VERSION
from .db import delete_project, get_project, list_projects, upsert_project
from .models import (AGENT_NAMES, PROJECT_TYPES, THEMES, AgentRun, BuildRun,
                     ProjectCreate, ProjectImport, ProjectInit, SettingsUpdate)
from .state import AppState

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(title=f"{APP_NAME} 项目坞", version=APP_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api = APIRouter(prefix="/api")
    app.state.pd_state = state

    def _resolve_project(pid: str) -> dict:
        row = get_project(state.conn, pid)
        if row and row.get("excluded"):
            raise HTTPException(status_code=404, detail="项目不存在")
        if row and Path(row["path"]).is_dir():
            return row
        p = state.settings.root / pid
        if p.is_dir():
            return {"id": pid, "name": pid, "type": "其他", "path": str(p), "description": ""}
        raise HTTPException(status_code=404, detail="项目不存在")

    @api.get("/health")
    def health() -> dict:
        return {"ok": True, "app": APP_NAME, "version": APP_VERSION, "root": str(state.settings.root)}

    @api.get("/settings")
    def get_settings() -> dict:
        return state.settings.as_dict()

    @api.put("/settings")
    def put_settings(payload: SettingsUpdate) -> dict:
        if payload.agent is not None and payload.agent not in AGENT_NAMES:
            raise HTTPException(status_code=400, detail="未知的 agent")
        if payload.theme is not None and payload.theme not in THEMES:
            raise HTTPException(status_code=400, detail="未知的主题")
        return state.settings.update(root=payload.root, agent=payload.agent, theme=payload.theme)

    @api.get("/presets")
    def list_presets() -> list[dict]:
        return [{
            "type": t,
            "label": spec["label"],
            "description": spec["description"],
            "files": list(spec.get("files", {}).keys()),
            "dirs": list(spec.get("dirs", [])),
            "git": spec.get("git", True),
        } for t, spec in presets.PRESETS.items()]

    @api.get("/projects")
    def list_all() -> list[dict]:
        root = state.settings.root
        root.mkdir(parents=True, exist_ok=True)
        db_rows = {p["id"]: p for p in list_projects(state.conn)}
        projects = scanner.scan_root(root, db_rows)
        known = {p["id"] for p in projects}
        for proj in projects:
            if proj["id"] not in db_rows or db_rows[proj["id"]].get("excluded"):
                upsert_project(state.conn, proj["id"], proj["name"], proj["type"],
                               proj["path"], proj["description"], imported=False)
        for row in list_projects(state.conn):
            if row["excluded"]:
                continue
            if row["imported"] and row["id"] not in known and Path(row["path"]).is_dir():
                parsed = scanner.parse_project_dir(row["id"])
                row["title"] = parsed[2] if parsed else row["id"]
                row["version"] = versioning.read_version(Path(row["path"]))
                row["has_git"] = (Path(row["path"]) / ".git").exists()
                projects.append(row)
        return projects

    @api.post("/projects", status_code=201)
    def create_project(payload: ProjectCreate) -> dict:
        root = state.settings.root
        root.mkdir(parents=True, exist_ok=True)
        ptype = payload.type if payload.type in PROJECT_TYPES else "其他"
        folder_name = scanner.make_folder_name(root, ptype, payload.name)
        project_path = root / folder_name
        if project_path.exists():
            raise HTTPException(status_code=409, detail="同名项目已存在")
        preset_result = None
        if payload.preset:
            preset_result = presets.apply_preset(project_path, ptype, payload.name, payload.description, git=True)
        else:
            project_path.mkdir(parents=True, exist_ok=True)
        upsert_project(state.conn, folder_name, folder_name, ptype, str(project_path),
                       payload.description, imported=False)
        return {
            "id": folder_name,
            "name": folder_name,
            "type": ptype,
            "title": payload.name,
            "path": str(project_path),
            "description": payload.description,
            "preset": preset_result,
            "version": versioning.read_version(project_path),
        }

    @api.post("/projects/import", status_code=201)
    def import_project(payload: ProjectImport) -> dict:
        try:
            return scanner.import_folder(state.conn, Path(payload.path), payload.type, payload.description)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @api.delete("/projects/{pid}")
    def remove_project(pid: str) -> dict:
        delete_project(state.conn, pid)
        return {"ok": True}

    @api.post("/projects/{pid}/init")
    def init_project(pid: str, payload: ProjectInit) -> dict:
        proj = _resolve_project(pid)
        ptype = payload.type if payload.type in PROJECT_TYPES else proj.get("type", "其他")
        parsed = scanner.parse_project_dir(pid)
        title = payload.name or (parsed[2] if parsed else proj["name"])
        description = payload.description if payload.description is not None else proj.get("description", "")
        result = presets.apply_preset(Path(proj["path"]), ptype, title, description, git=payload.git)
        upsert_project(state.conn, pid, proj["name"], ptype, proj["path"], description,
                       imported=bool(proj.get("imported", False)))
        return result

    @api.get("/projects/{pid}/versions")
    def get_versions(pid: str) -> dict:
        proj = _resolve_project(pid)
        return versioning.project_version_summary(Path(proj["path"]))

    @api.get("/projects/{pid}/builds")
    def list_builds(pid: str) -> list[dict]:
        proj = _resolve_project(pid)
        return builder.find_build_scripts(Path(proj["path"]))

    @api.post("/projects/{pid}/build")
    def run_build(pid: str, payload: BuildRun) -> dict:
        proj = _resolve_project(pid)
        scripts = {s["name"]: s for s in builder.find_build_scripts(Path(proj["path"]))}
        script = scripts.get(payload.script)
        if not script:
            raise HTTPException(status_code=404, detail="构建脚本不存在")
        job = state.jobs.start(builder.command_for(script), str(Path(proj["path"])), f"构建 {script['name']}")
        return {"job_id": job.id, "script": script["name"]}

    @api.post("/projects/{pid}/open")
    def open_project(pid: str) -> dict:
        proj = _resolve_project(pid)
        if os.name != "nt":
            raise HTTPException(status_code=400, detail="当前平台暂不支持打开文件夹")
        os.startfile(proj["path"])  # type: ignore[attr-defined]
        return {"ok": True}

    @api.get("/agents")
    def list_agents() -> list[dict]:
        return [{"name": k, "label": v["label"], "hint": v["hint"]} for k, v in AGENTS.items()]

    @api.post("/agent/run")
    def run_agent(payload: AgentRun) -> dict:
        proj = _resolve_project(payload.project_id)
        agent = payload.agent if payload.agent in AGENT_NAMES else "claude"
        prompt = system_prompt(proj["name"], proj["path"]) + "\n\n用户要求：" + payload.prompt
        cmd = build_command(agent, prompt)
        job = state.jobs.start(cmd, str(Path(proj["path"])), f"AI · {AGENTS[agent]['label']}")
        return {"job_id": job.id, "agent": agent}

    @api.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        status = state.jobs.status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        return status

    @api.get("/jobs/{job_id}/stream")
    async def job_stream(job_id: str, request: Request):
        job = state.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")

        async def gen():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        item = await asyncio.to_thread(job.queue.get, timeout=0.5)
                    except (asyncio.TimeoutError, queue_module.Empty):
                        continue
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    if item.get("type") == "end":
                        break
            except Exception:  # noqa: BLE001
                pass

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.include_router(api)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
    else:
        @app.get("/")
        def web_missing() -> JSONResponse:
            return JSONResponse({"ok": True, "note": "web/ 前端目录缺失，仅 API 可用"})

    return app
