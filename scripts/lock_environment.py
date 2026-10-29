"""Record the installed runtime dependency closure; review upgrades before regenerating."""

import importlib.metadata
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
pending = [Requirement(item).name for item in config["project"]["dependencies"]]
locked = {}
while pending:
    name = canonicalize_name(pending.pop())
    if name in locked:
        continue
    dist = importlib.metadata.distribution(name)
    locked[name] = dist.version
    for raw in dist.requires or []:
        requirement = Requirement(raw)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            pending.append(requirement.name)
lines = ["# Runtime closure from the validated Python 3.12 environment; no credentials."]
for name, version in sorted(locked.items()):
    marker = '; sys_platform == "win32"' if name in {"pywin32", "colorama"} else ""
    lines.append(f"{name}=={version}{marker}")
Path("requirements.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"locked {len(locked)} distributions")
