import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, Field, StringConstraints

from paperpilot.config import Settings
from paperpilot.ingest import MAX_PDF_BYTES, ingest_github, ingest_pdf
from paperpilot.store import Store
from paperpilot.workflow import build_graph

logger = logging.getLogger("paperpilot")


class RepositoryInput(BaseModel):
    url: str = Field(max_length=300)


class TaskInput(BaseModel):
    source_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=2000)]


class Approval(BaseModel):
    approved: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    config.prepare()
    store = Store(config.data_dir)
    tasks: dict[str, asyncio.Task] = {}
    limit = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Interrupted jobs are explicit; pending approval checkpoints remain resumable after restart.
        for job in store.jobs():
            if job["status"] in {"queued", "running"}:
                job.update(status="failed", error="服务重启中断任务，请重新创建；已有记录已保留")
                store.save_job(job)
        async with AsyncSqliteSaver.from_conn_string(str(config.data_dir / "checkpoints.sqlite")) as saver:
            app.state.graph = build_graph(config, store, saver)
            yield
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    app = FastAPI(title="PaperPilot Agent", version="0.1.0", lifespan=lifespan)
    app.state.store = store

    async def run(job_id: str, value) -> None:
        async with limit:
            job = store.job(job_id)
            job["status"] = "running"
            store.save_job(job)
            try:
                result = await app.state.graph.ainvoke(value, {"configurable": {"thread_id": job_id},
                                                              "recursion_limit": 20})
                if result.get("__interrupt__"):
                    job.update(status="awaiting_approval", approval=result["__interrupt__"][0].value)
                    store.event(job_id, "awaiting_approval", job["approval"])
                elif result.get("denied"):
                    job.update(status="cancelled")
                    store.event(job_id, "cancelled", "用户拒绝模型数据传输")
                else:
                    job.update(status="completed", markdown=result["markdown"],
                               evidence=result["evidence"], plan=result["actions"], skill=result["skill"]["name"])
                    store.event(job_id, "completed", "报告已生成")
            except Exception as exc:
                # The job boundary owns error handling: record failure, never invent a success report.
                logger.exception("Task %s failed", job_id)
                job.update(status="failed", error=(str(exc) if isinstance(exc, ValueError) else
                           f"{type(exc).__name__}：任务失败，请检查服务日志与模型连接"))
                store.event(job_id, "failed", job["error"])
            store.save_job(job)

    def schedule(job_id: str, value) -> None:
        task = asyncio.create_task(run(job_id, value))
        tasks[job_id] = task
        task.add_done_callback(lambda _: tasks.pop(job_id, None))

    @app.exception_handler(KeyError)
    async def missing_source(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid_input(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error(request, exc):
        from fastapi.responses import JSONResponse
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        return JSONResponse(status_code=502, content={"detail": f"GitHub 访问失败（HTTP {status}），检查网络、仓库地址或限流"})

    @app.get("/health")
    def health():
        return dict(status="ok", mode=config.mode, model=config.model if config.mode == "live" else None,
                    retrieval="character-hashing sparse vectors", version="0.1.0")

    @app.post("/sources/pdf", status_code=201)
    async def upload_pdf(file: Annotated[UploadFile, File()]):
        data = await file.read(MAX_PDF_BYTES + 1)
        # Parsing is CPU work; keep the API event loop available for job status requests.
        return await asyncio.to_thread(ingest_pdf, data, (file.filename or "paper.pdf")[:200], store)

    @app.post("/sources/github", status_code=201)
    async def upload_repository(body: RepositoryInput):
        async with httpx.AsyncClient(timeout=25, follow_redirects=False,
                                     headers={"User-Agent": "PaperPilot-Agent/0.1"}) as client:
            return await ingest_github(body.url, store, client)

    @app.get("/sources/{source_id}")
    def source(source_id: str):
        return store.source(source_id)

    @app.post("/tasks", status_code=202)
    async def create_task(body: TaskInput):
        store.source(body.source_id)
        if len(tasks) >= 8:
            raise HTTPException(429, "队列已满，请等待已有任务完成")
        job_id = uuid4().hex
        job = dict(id=job_id, source_id=body.source_id, question=body.question, mode=config.mode,
                   status="queued", created_at=datetime.now(UTC).isoformat())
        store.save_job(job)
        store.event(job_id, "queued", dict(mode=config.mode))
        schedule(job_id, dict(job_id=job_id, source_id=body.source_id, question=body.question))
        return job

    @app.get("/tasks")
    def jobs():
        return store.jobs()

    @app.get("/tasks/{job_id}")
    def job(job_id: str):
        return dict(store.job(job_id), events=store.events(job_id))

    @app.post("/tasks/{job_id}/approval", status_code=202)
    async def approve(job_id: str, body: Approval):
        job = store.job(job_id)
        if job["status"] != "awaiting_approval" or job_id in tasks:
            raise HTTPException(409, "任务当前不等待确认")
        if len(tasks) >= 8:
            raise HTTPException(429, "队列已满")
        job["status"] = "queued"
        store.save_job(job)
        store.event(job_id, "approval", dict(approved=body.approved))
        schedule(job_id, Command(resume=body.approved))
        return job

    @app.get("/tasks/{job_id}/report", response_class=PlainTextResponse)
    def download(job_id: str):
        job = store.job(job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "报告尚未完成")
        return PlainTextResponse(job["markdown"], media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="paperpilot-{job_id}.md"'})

    return app
