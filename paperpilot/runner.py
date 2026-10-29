"""Opt-in CPU Docker execution. The web application never mounts a Docker socket."""

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

import httpx
from pydantic import Field, field_validator

from paperpilot.experiments import (
    Contract,
    Measurement,
    Reference,
    ResultSubmission,
    compare_results,
    content_hash,
)
from paperpilot.ingest import parse_github_url


class Recipe(Contract):
    schema_version: str = "1"
    name: str = Field(min_length=1, max_length=200)
    repository_url: str = Field(max_length=300)
    repository_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    image: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_./:@+-]{0,200}$")
    adapter: str = Field(max_length=200)
    command: list[str] = Field(min_length=1, max_length=40)
    timeout_seconds: int = Field(default=180, ge=5, le=1800)
    memory_mb: int = Field(default=2048, ge=128, le=8192)
    cpus: float = Field(default=1, ge=0.25, le=4)
    scope: str = Field(pattern=r"^(smoke|evaluation|full)$")
    reference: Reference
    reference_reviewed: bool = False
    notes: str = Field(default="", max_length=3000)

    @field_validator("repository_url")
    @classmethod
    def github_only(cls, value: str) -> str:
        parse_github_url(value)
        return value

    @field_validator("adapter")
    @classmethod
    def relative_adapter(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or path.suffix != ".py":
            raise ValueError("adapter 必须是配方目录内的相对 .py 文件")
        return value


def docker(*args: str, timeout: int = 30) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout).stdout.strip()


def review_recipe(path: Path) -> tuple[Recipe, dict]:
    recipe = Recipe.model_validate_json(path.read_text(encoding="utf-8"))
    adapter = (path.parent / recipe.adapter).resolve()
    if not adapter.is_relative_to(path.parent.resolve()):
        raise ValueError("adapter 必须位于配方目录内")
    adapter_hash = hashlib.sha256(adapter.read_bytes()).hexdigest()
    image_id = docker("image", "inspect", recipe.image, "--format", "{{.Id}}")
    review = dict(recipe=recipe.model_dump(), adapter_sha256=adapter_hash, image_id=image_id)
    return recipe, dict(**review, approval_digest=content_hash(review))


def extract_snapshot(data: bytes, destination: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
            raise ValueError("运行快照最多 10000 个文件、解压后 100 MB")
        prefix = entries[0].filename.partition("/")[0]
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in entry.filename
                    or name.parts[0] != prefix or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("归档包含非法路径或符号链接")
            relative = Path(*name.parts[1:])
            if not relative.parts or entry.is_dir():
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))


def container_arguments(recipe: Recipe, review: dict, run_dir: Path, name: str) -> list[str]:
    return ["create", "--name", name, "--pull", "never", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128",
            "--memory", f"{recipe.memory_mb}m", "--memory-swap", f"{recipe.memory_mb}m",
            "--cpus", str(recipe.cpus), "--user", "10001:10001",
            "--log-driver", "local", "--log-opt", "max-size=10m", "--log-opt", "max-file=1",
            "--log-opt", "compress=false",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--workdir", "/workspace",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "OPENBLAS_NUM_THREADS=1",
            "--env", "OMP_NUM_THREADS=1", "--env", "PAPERPILOT_OUTPUT_DIR=/output",
            "--mount", f"type=bind,source={run_dir / 'source'},target=/workspace,readonly",
            "--mount", f"type=bind,source={run_dir / 'adapter'},target=/recipe,readonly",
            "--mount", f"type=bind,source={run_dir / 'output'},target=/output",
            review["image_id"], *recipe.command]


def execute_recipe(path: Path, approval: str, runs_dir: Path) -> dict:
    recipe, review = review_recipe(path)
    if approval != review["approval_digest"]:
        raise ValueError("批准摘要不匹配；请重新 inspect 并核对配方、适配器和镜像")
    run_id = uuid4().hex
    run_dir = (runs_dir / run_id).resolve()
    run_dir.mkdir(parents=True, mode=0o700)
    for directory in ["source", "adapter", "output"]:
        (run_dir / directory).mkdir()
    os.chmod(run_dir / "output", 0o777)
    (run_dir / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    record = dict(id=run_id, started_at=datetime.now(UTC).isoformat(), status="running", review=review)
    name = f"paperpilot-run-{run_id}"
    started = time.monotonic()
    created = False
    try:
        shutil.copyfile(path.parent / recipe.adapter, run_dir / "adapter" / "adapter.py")
        if hashlib.sha256((run_dir / "adapter" / "adapter.py").read_bytes()).hexdigest() != review["adapter_sha256"]:
            raise ValueError("适配器已变化，请重新审批")
        owner, repository = parse_github_url(recipe.repository_url)
        archive = bytearray()
        with httpx.stream("GET", f"https://codeload.github.com/{owner}/{repository}/zip/{recipe.repository_commit}",
                          timeout=60, follow_redirects=False) as response:
            response.raise_for_status()
            for block in response.iter_bytes():
                archive.extend(block)
                if len(archive) > 20 * 1024 * 1024:
                    raise ValueError("运行快照压缩后超过 20 MB")
        extract_snapshot(bytes(archive), run_dir / "source")
        record["source_archive_sha256"] = hashlib.sha256(archive).hexdigest()
        docker(*container_arguments(recipe, review, run_dir, name))
        created = True
        docker("start", name)
        exit_code = int(docker("wait", name, timeout=recipe.timeout_seconds))
        record.update(exit_code=exit_code, status="completed" if exit_code == 0 else "failed")
        if exit_code == 0:
            metrics_path = run_dir / "output" / "metrics.json"
            if metrics_path.is_symlink() or metrics_path.stat().st_size > 1024 * 1024:
                raise ValueError("metrics.json 必须是最多 1 MB 的普通文件")
            measured_bytes = metrics_path.read_bytes()
            measurement = Measurement.model_validate_json(measured_bytes)
            submission = ResultSubmission(reference=recipe.reference, observed=measurement, scope=recipe.scope,
                repository_commit=recipe.repository_commit, reference_reviewed=recipe.reference_reviewed,
                artifact_sha256=hashlib.sha256(measured_bytes).hexdigest(), notes=recipe.notes)
            record.update(submission=submission.model_dump(), comparison=compare_results(submission))
            (run_dir / "comparison-input.json").write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    except subprocess.TimeoutExpired:
        record.update(status="timed_out", error="实验超过批准的时间预算")
    except (subprocess.CalledProcessError, OSError, ValueError, httpx.HTTPError, zipfile.BadZipFile) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        record.update(status="failed", error=detail[:2000])
    finally:
        if created:
            # Lifecycle boundary: stop even a timed-out process before collecting its bounded logs.
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=15)
            logs = subprocess.run(["docker", "logs", "--tail", "10000", name], capture_output=True, timeout=20)
            (run_dir / "stdout.log").write_bytes(logs.stdout)
            (run_dir / "stderr.log").write_bytes(logs.stderr)
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=15)
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        record["artifact_hashes"] = {str(p.relative_to(run_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in [run_dir / "review.json", run_dir / "stdout.log", run_dir / "stderr.log"]
                                    if p.exists()}
        (run_dir / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(record, run_directory=str(run_dir))
