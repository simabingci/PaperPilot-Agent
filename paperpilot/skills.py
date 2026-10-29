from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    tools: tuple[str, ...]


def load_skill(kind: str) -> Skill:
    name = "paper-analysis" if kind == "paper" else "repository-analysis"
    path = Path(__file__).parent / "skills" / name / "SKILL.md"
    _, header, body = path.read_text(encoding="utf-8").split("---", 2)
    metadata = yaml.safe_load(header)
    return Skill(metadata["name"], metadata["description"], body.strip(),
                 tuple(metadata["allowed-tools"].split()))
