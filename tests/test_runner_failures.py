import io
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from paperpilot.runner import execute_recipe, review_recipe


@pytest.mark.parametrize("failure", ["download", "timeout", "missing_metrics"])
def test_runner_records_failure_without_success_comparison(tmp_path, monkeypatch, failure):
    path = tmp_path / "recipe.json"
    path.write_bytes(Path("examples/tcn-adding/recipe.json").read_bytes())
    (tmp_path / "adapter.py").write_text("print('fixture')", encoding="utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("repo/", "")
        archive.writestr("repo/model.py", "# test fixture")
    calls = []

    def docker(*args, **kwargs):
        calls.append(args[0])
        if args[0] == "image":
            return "sha256:fixed"
        if args[0] == "wait":
            if failure == "timeout":
                raise subprocess.TimeoutExpired("docker wait", 5)
            return "0"
        return "ok"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            if failure == "download":
                raise httpx.ConnectError("fixture network failure")

        def iter_bytes(self):
            yield buffer.getvalue()

    monkeypatch.setattr("paperpilot.runner.docker", docker)
    monkeypatch.setattr("paperpilot.runner.httpx.stream", lambda *a, **kw: Response())
    monkeypatch.setattr("paperpilot.runner.subprocess.run", lambda *a, **kw: SimpleNamespace(stdout=b"log", stderr=b""))
    _, review = review_recipe(path)
    run = execute_recipe(path, review["approval_digest"], tmp_path / "runs")
    directory = Path(run["run_directory"])
    saved = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    assert saved["status"] == ("timed_out" if failure == "timeout" else "failed")
    assert "comparison" not in saved and not (directory / "comparison-input.json").exists()
    assert "create" not in calls if failure == "download" else (directory / "stdout.log").exists()
