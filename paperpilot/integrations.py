"""Local client adapters: one skill and evidence store, host-specific discovery/config."""

import json
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

AGENTS = ("codex", "claude-code", "deepseek-harness", "workbuddy", "generic")
SKILL_ROOTS = {"codex": ".agents/skills", "claude-code": ".claude/skills",
               "deepseek-harness": ".dsh/skills", "workbuddy": "data/integrations/workbuddy/skills",
               "generic": "data/integrations/generic/skills"}


def install_skill(agent: str, dest: Path | None, data_dir: Path, update: bool) -> dict:
    target = (dest or Path(SKILL_ROOTS[agent])).resolve() / "paperpilot-study"
    source = Path(__file__).parent / "skills" / "paperpilot-study"
    shutil.copytree(source, target, dirs_exist_ok=update)
    runtime = dict(command=[sys.executable, "-X", "utf8", "-m", "paperpilot.cli"],
                   data_dir=str(data_dir.resolve()))
    (target / "references/runtime.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    result = dict(agent=agent, installed=str(target),
                  note="Load paperpilot-study in the client; allow local commands to save learning progress.")
    if agent == "workbuddy":
        path = target / "SKILL.md"
        _, header, body = path.read_text(encoding="utf-8").split("---", 2)
        metadata = yaml.safe_load(header)
        metadata.update(display_name="PaperPilot 论文学习", display_name_en="PaperPilot Study",
                        description_zh="结合论文原文逐步讲解方法和实验，保存问答与反馈。",
                        description_en=metadata["description"], version="0.3.0", author="PaperPilot contributors")
        path.write_text("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
                        + "---" + body, encoding="utf-8")
        archive = target.parent / "paperpilot-study.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
            # Package only maintained resources, never unrelated user files in an updated install.
            for relative in [Path("SKILL.md"), Path("references/runtime.json"),
                             *[p.relative_to(source) for p in source.glob("references/*.md")]]:
                bundle.write(target / relative, str(Path(target.name) / relative))
        result.update(archive=str(archive), note="Import this local skill ZIP in WorkBuddy; do not publish it.")
    return result


def mcp_config(agent: str, data_dir: Path) -> str:
    server = dict(command=sys.executable, args=["-X", "utf8", "-m", "paperpilot.mcp_server"],
                  env=dict(PAPERPILOT_DATA_DIR=str(data_dir.resolve()), PAPERPILOT_MODE="mock",
                           PYTHONUTF8="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1"))
    if agent == "deepseek-harness":
        return yaml.safe_dump([dict(id="mcp-paperpilot", name="@deepseek-ai/dsh-mcp-client",
                                   config=dict(serverName="paperpilot", transport="stdio", **server))],
                              allow_unicode=True, sort_keys=False)
    return json.dumps(dict(mcpServers=dict(paperpilot=dict(type="stdio", **server))),
                      ensure_ascii=False, indent=2) + "\n"
