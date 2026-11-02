"""Local client adapters: one skill and evidence store, host-specific discovery/config."""

import json
import os
import shutil
import sys
from datetime import datetime
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


def dsh_patch_path(profile: str = "desktop") -> Path:
    home = Path(os.getenv("DSH_HOME") or Path.home() / ".dsh")
    return home / "profiles" / profile / "cordis.patch.yml"


def codex_config_path() -> Path:
    home = Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")
    return home / "config.toml"


def _toml_server_block(server_name: str, command: str, args: list[str], env: dict[str, str]) -> str:
    lines = [f"[mcp_servers.{server_name}]",
             f"command = {json.dumps(command, ensure_ascii=False)}",
             "args = [" + ", ".join(json.dumps(item, ensure_ascii=False) for item in args) + "]",
             "", f"[mcp_servers.{server_name}.env]"]
    lines.extend(f'"{key}" = {json.dumps(value, ensure_ascii=False)}' for key, value in env.items())
    return "\n".join(lines) + "\n"


def _connect_codex(data_dir: Path, force: bool, dry_run: bool) -> dict:
    import tomllib

    path = codex_config_path()
    if not path.exists():
        raise ValueError(f"未找到 Codex 配置：{path}（先至少运行一次 Codex）")
    text = path.read_text(encoding="utf-8-sig")
    server = dict(command=sys.executable, args=["-X", "utf8", "-m", "paperpilot.mcp_server"],
                  env=dict(PAPERPILOT_DATA_DIR=str(data_dir.resolve()), PAPERPILOT_MODE="mock",
                           PYTHONUTF8="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1"))
    block = _toml_server_block("paperpilot", server["command"], server["args"], server["env"])
    parsed = tomllib.loads(text)
    exists = "paperpilot" in parsed.get("mcp_servers", {})
    if dry_run:
        return dict(status="preview", config=str(path), content=block,
                    note="未写入；去掉 --dry-run 才会修改配置")
    if exists and not force:
        return dict(status="already_configured", config=str(path),
                    note="mcp_servers.paperpilot 已存在；需要更新路径时加 --force")
    backup = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    backup.write_text(text, encoding="utf-8")
    new_text = text if text.endswith("\n") else text + "\n"
    if exists:
        kept, skip = [], False
        for line in new_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                skip = stripped.startswith("[mcp_servers.paperpilot")
            if not skip:
                kept.append(line)
        new_text = "\n".join(kept).rstrip("\n") + "\n\n" + block
        note = "已替换既有 mcp_servers.paperpilot 表"
    else:
        new_text = new_text.rstrip("\n") + "\n\n" + block
        note = "已追加 mcp_servers.paperpilot，原有配置未改动"
    path.write_text(new_text, encoding="utf-8")
    try:
        reloaded = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        if "paperpilot" not in reloaded.get("mcp_servers", {}):
            raise ValueError("写入后未找到 paperpilot 条目")
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        shutil.copyfile(backup, path)
        raise ValueError(f"写入后校验失败，已从备份恢复：{exc}") from exc
    return dict(status="written", config=str(path), backup=str(backup), note=note,
                next_step="重启 Codex 后，新会话即可调用 paperpilot 的检索工具")


def _is_paperpilot_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("id") == "mcp-paperpilot":
        return True
    return (str(entry.get("name", "")).endswith("dsh-mcp-client")
            and (entry.get("config") or {}).get("serverName") == "paperpilot")


def connect_agent(agent: str, data_dir: Path, profile: str = "desktop", force: bool = False,
                  dry_run: bool = False) -> dict:
    """Write the MCP entry into the host agent's own config, with a timestamped backup.

    This is the zero-key path: the host agent supplies the reasoning, PaperPilot only
    supplies evidence over MCP. Other clients keep using `mcp-config` to export a fragment.
    """
    if agent == "codex":
        return _connect_codex(data_dir, force, dry_run)
    if agent != "deepseek-harness":
        raise ValueError("目前只自动写入 deepseek-harness 与 codex；其他客户端请用 paperpilot mcp-config 导出片段")
    patch = dsh_patch_path(profile)
    if not patch.exists():
        raise ValueError(f"未找到 DSH profile 配置：{patch}（先至少启动一次 DSH）")
    text = patch.read_text(encoding="utf-8")
    entries = yaml.safe_load(text) or []
    if not isinstance(entries, list):
        raise ValueError(f"{patch} 不是 YAML 列表，未做任何修改")
    block = mcp_config("deepseek-harness", data_dir)
    existing = [entry for entry in entries if _is_paperpilot_entry(entry)]
    if existing and not force:
        return dict(status="already_configured", config=str(patch),
                    note="paperpilot 条目已存在；需要更新路径时加 --force")
    backup = patch.with_name(f"{patch.name}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    backup.write_text(text, encoding="utf-8")
    if existing:
        updated = [entry for entry in entries if not _is_paperpilot_entry(entry)]
        new_text = yaml.safe_dump(updated, allow_unicode=True, sort_keys=False)
        new_text += block
        note = "已替换既有 paperpilot 条目（重写整份配置，注释可能丢失）"
    else:
        new_text = text if text.endswith("\n") else text + "\n"
        new_text += ("" if not new_text.strip() else "\n") + block
        note = "已追加 paperpilot 条目，原有配置未改动"
    patch.write_text(new_text, encoding="utf-8")
    try:
        reloaded = yaml.safe_load(patch.read_text(encoding="utf-8")) or []
        if sum(1 for entry in reloaded if _is_paperpilot_entry(entry)) != 1:
            raise ValueError("写入后校验失败：paperpilot 条目数量不是 1")
    except (yaml.YAMLError, ValueError) as exc:
        shutil.copyfile(backup, patch)
        raise ValueError(f"写入后校验失败，已从备份恢复：{exc}") from exc
    return dict(status="written", config=str(patch), backup=str(backup), note=note,
                next_step="重启 DSH 后，新会话里即可直接调用 paperpilot 的检索工具")
