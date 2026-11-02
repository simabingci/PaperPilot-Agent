"""Environment self-check: turn the most common setup failures into one actionable line each."""

import shutil
import subprocess
import sys
import tempfile

from paperpilot.config import Settings

OK, WARN, FAIL = "ok", "warn", "fail"


def _python() -> dict:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < (3, 12):
        return dict(name="python", status=FAIL, detail=version, hint="需要 Python 3.12 或更高版本")
    return dict(name="python", status=OK, detail=version, hint="")


def _data_dir(settings: Settings) -> dict:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=settings.data_dir, prefix=".doctor-", delete=True):
            pass
    except OSError as exc:
        return dict(name="data_dir", status=FAIL, detail=str(settings.data_dir),
                    hint=f"数据目录不可写：{exc}")
    from paperpilot.store import Store

    try:
        version = Store(settings.data_dir).schema_version()
    except (OSError, ValueError) as exc:
        return dict(name="data_dir", status=FAIL, detail=str(settings.data_dir), hint=str(exc))
    return dict(name="data_dir", status=OK, detail=f"{settings.data_dir}（schema v{version}）", hint="")


def _docker() -> dict:
    if shutil.which("docker") is None:
        return dict(name="docker", status=WARN, detail="未找到 docker 命令",
                    hint="只有执行实验配方时才需要 Docker；分析与讲解不需要")
    try:
        completed = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                   capture_output=True, text=True, timeout=15, encoding="utf-8")
    except (OSError, subprocess.SubprocessError) as exc:
        return dict(name="docker", status=WARN, detail="docker 命令不可用", hint=str(exc)[:200])
    if completed.returncode != 0:
        return dict(name="docker", status=WARN, detail="Docker 守护进程未运行",
                    hint="启动 Docker Desktop 或 systemd 服务后再执行实验")
    return dict(name="docker", status=OK, detail=f"server {completed.stdout.strip()}", hint="")


def _model(settings: Settings) -> dict:
    if settings.mode != "live":
        return dict(name="model", status=OK, detail="mock（不调用模型）",
                    hint="需要模型分析时设置 PAPERPILOT_MODE=live 与模型参数")
    missing = [name for name, value in [("OPENAI_MODEL", settings.model),
                                        ("OPENAI_API_KEY", settings.api_key.get_secret_value()),
                                        ("OPENAI_BASE_URL", settings.base_url)] if not value]
    if missing:
        return dict(name="model", status=FAIL, detail="live 模式缺少配置",
                    hint="缺少：" + ", ".join(missing))
    return dict(name="model", status=OK,
                detail=f"{settings.model} @ {settings.base_url}", hint="")


def _pdf_engine() -> dict:
    try:
        import pypdf
        import pypdfium2  # noqa: F401
    except ImportError as exc:
        return dict(name="pdf", status=FAIL, detail="PDF 依赖缺失", hint=str(exc))
    return dict(name="pdf", status=OK, detail=f"pypdf {pypdf.__version__}", hint="")


def _auth(settings: Settings) -> dict:
    if settings.api_token.get_secret_value():
        return dict(name="api_auth", status=OK, detail="已启用 Bearer token", hint="")
    return dict(name="api_auth", status=WARN, detail="未设置 PAPERPILOT_API_TOKEN",
                hint="仅在本机绑定 127.0.0.1 时可接受；对外暴露前请设置 token")


def run_checks(settings: Settings) -> dict:
    checks = [_python(), _data_dir(settings), _pdf_engine(), _docker(), _model(settings), _auth(settings)]
    statuses = {check["status"] for check in checks}
    overall = FAIL if FAIL in statuses else WARN if WARN in statuses else OK
    return dict(overall=overall, checks=checks,
                next_step=next((c["hint"] for c in checks if c["status"] == FAIL),
                               next((c["hint"] for c in checks if c["status"] == WARN), "")))


if __name__ == "__main__":
    settings = Settings()
    result = run_checks(settings)
    for check in result["checks"]:
        marker = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}[check["status"]]
        print(f"{marker} {check['name']}: {check['detail']}" + (f" -> {check['hint']}" if check["hint"] else ""))
    print("overall:", result["overall"])
    raise SystemExit(0 if result["overall"] != FAIL else 1)