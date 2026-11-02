"""Explicit experimental protocols and deterministic, unit-aware result comparison."""

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from paperpilot.store import Store


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Protocol(Contract):
    dataset: str = Field(min_length=1, max_length=800)
    split: str = Field(min_length=1, max_length=800)
    preprocessing: str = Field(min_length=1, max_length=800)
    model: str = Field(min_length=1, max_length=800)
    training_budget: str = Field(min_length=1, max_length=800)
    evaluation: str = Field(min_length=1, max_length=800)


class Target(Contract):
    name: str = Field(min_length=1, max_length=120)
    value: float
    unit: str = Field(min_length=1, max_length=80)
    direction: Literal["higher", "lower"]
    absolute_tolerance: float = Field(default=0, ge=0)
    relative_tolerance: float = Field(default=0, ge=0, le=1)
    paper_location: str = Field(min_length=1, max_length=500)


class Reference(Contract):
    paper_title: str = Field(min_length=1, max_length=500)
    paper_url: str = Field(min_length=1, max_length=500)
    paper_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    protocol: Protocol
    metrics: list[Target] = Field(min_length=1, max_length=30)


class Measurement(Contract):
    protocol: Protocol
    metrics: dict[str, float] = Field(min_length=1, max_length=30)
    units: dict[str, str] = Field(min_length=1, max_length=30)


class ResultSubmission(Contract):
    reference: Reference
    observed: Measurement
    scope: Literal["smoke", "evaluation", "full"]
    repository_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    reference_reviewed: bool = False
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    notes: str = Field(default="", max_length=3000)


def content_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


UNKNOWN_MARKERS = {"unknown", "n/a", "na", "tbd", "?", "未确认", "待确认", "不确定", "未知", ""}


def normalize_text(value: str) -> str:
    """Compare protocol text by content, not by spacing or capitalisation."""
    return re.sub(r"[\s_\-—–]+", "", value).casefold()


def is_unknown(value: str) -> bool:
    return value.strip().casefold() in UNKNOWN_MARKERS


def _looks_like_filename(title: str) -> bool:
    return title.strip().casefold().endswith((".pdf", ".docx", ".md", ".txt"))


def same_paper(study_title: str, reference_title: str) -> bool:
    """Titles that are only file names carry no identity and are not compared."""
    if _looks_like_filename(study_title) or _looks_like_filename(reference_title):
        return True
    return normalize_text(study_title) == normalize_text(reference_title)


def compare_results(submission: ResultSubmission) -> dict:
    expected, actual = submission.reference.protocol.model_dump(), submission.observed.protocol.model_dump()
    differences = [dict(field=name, paper=value, actual=actual[name]) for name, value in expected.items()
                   if (normalize_text(value) != normalize_text(actual[name])
                       or is_unknown(value) or is_unknown(actual[name]))]
    reasons = []
    if differences:
        reasons.append("实验协议不一致或存在未确认项")
    if submission.scope == "smoke":
        reasons.append("本次仅为小规模流程验证")
    if not submission.reference_reviewed:
        reasons.append("论文基准尚未人工核对")
    rows = []
    for target in submission.reference.metrics:
        measured = submission.observed.metrics.get(target.name)
        unit = submission.observed.units.get(target.name)
        delta = measured - target.value if measured is not None and unit == target.unit else None
        row_reasons = list(reasons)
        if unit != target.unit:
            row_reasons.append(f"单位不一致：{unit} / {target.unit}")
        tolerance = max(target.absolute_tolerance, abs(target.value) * target.relative_tolerance)
        status = ("missing" if measured is None else "not_comparable" if row_reasons else
                  "within_tolerance" if abs(delta) <= tolerance else "outside_tolerance")
        rows.append(dict(metric=target.name, paper=target.value, actual=measured, unit=target.unit,
                         delta=delta, tolerance=tolerance, direction=target.direction,
                         status=status, reasons=row_reasons, paper_location=target.paper_location))
    return dict(rows=rows, protocol_differences=differences,
                comparable=not reasons and all(r["status"] != "missing" and not r["reasons"] for r in rows),
                conclusion="按提交的协议与容差比较；不能单独证明论文已经完整复现。")


def comparison_markdown(result: dict) -> str:
    labels = {"within_tolerance": "容差内", "outside_tolerance": "超出容差",
              "not_comparable": "不可直接比较", "missing": "缺失指标"}
    lines = ["# 实验结果对照", "", "| 指标 | 论文 | 实测 | 单位 | 差值（实测−论文） | 状态 |",
             "|---|---:|---:|---|---:|---|"]
    for row in result["rows"]:
        lines.append(f"| {row['metric']} | {row['paper']:.8g} | {row['actual']} | {row['unit']} | "
                     f"{row['delta']} | {labels[row['status']]} |")
    lines.extend(["", "## 协议与边界", ""])
    for difference in result["protocol_differences"]:
        lines.append(f"- {difference['field']}：论文 `{difference['paper']}`；实测 `{difference['actual']}`")
    for row in result["rows"]:
        lines.append(f"- {row['metric']} 来源：{row['paper_location']}；" + "；".join(row["reasons"]))
    lines.extend(["", result["conclusion"]])
    return "\n".join(lines)


def record_result(store: Store, study_id: str, body: ResultSubmission, provenance: str) -> dict:
    study = store.source(study_id)
    if study["kind"] != "study":
        raise ValueError("需要复现工作区 ID")
    if study["metadata"]["repository"]["commit"] != body.repository_commit:
        raise ValueError("结果的代码 commit 与工作区不一致，请为该版本建立对应工作区")
    paper = store.source(study["metadata"]["paper_id"])
    warnings = []
    declared_sha = body.reference.paper_sha256
    stored_sha = paper["metadata"].get("sha256")
    if declared_sha and stored_sha and declared_sha != stored_sha:
        raise ValueError("结果的论文哈希与工作区论文不一致；请为该论文建立对应工作区")
    if not same_paper(paper["title"], body.reference.paper_title):
        # Titles are author-typed labels, so a mismatch is recorded, not treated as proof.
        warnings.append(f"论文标题与工作区不一致：工作区《{paper['title']}》，"
                        f"基准《{body.reference.paper_title}》；请人工确认是否为同一篇论文")
    comparison = compare_results(body)
    return store.save_result(study_id, dict(submission=body.model_dump(), comparison=comparison,
        markdown=comparison_markdown(comparison), provenance=provenance, warnings=warnings))
