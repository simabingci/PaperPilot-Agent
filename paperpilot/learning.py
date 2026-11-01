"""Local learning records. The calling agent teaches; this module never calls a model."""

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from paperpilot.store import Store


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    quote: str = Field(min_length=6, max_length=600)


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=10, max_length=5000)
    question: str = Field(min_length=2, max_length=800)
    evidence: list[Evidence] = Field(min_length=1, max_length=6)
    assumptions: list[str] = Field(default_factory=list, max_length=12)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment: Literal["understood", "needs_review", "uncertain"]
    feedback: str = Field(min_length=2, max_length=3000)
    evidence: list[Evidence] = Field(min_length=1, max_length=6)


def session(store: Store, session_id: str) -> dict:
    with store.connect() as db:
        row = db.execute("SELECT payload FROM learning WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise ValueError("学习记录不存在")
    return json.loads(row[0])


def sessions(store: Store) -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT payload FROM learning ORDER BY rowid DESC").fetchall()
    return [json.loads(row[0]) for row in rows]


def save(store: Store, record: dict) -> dict:
    record["updated_at"] = datetime.now(UTC).isoformat()
    with store.connect() as db:
        db.execute("INSERT INTO learning VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (record["id"], json.dumps(record, ensure_ascii=False)))
    return record


def start(store: Store, source_id: str, goal: str) -> dict:
    source = store.source(source_id)
    if source["kind"] not in {"paper", "study"}:
        raise ValueError("学习需要论文或论文与代码工作区")
    goal = goal.strip()
    if not 2 <= len(goal) <= 2000:
        raise ValueError("学习目标需为 2–2000 字符")
    return save(store, dict(id=uuid4().hex, source_id=source_id, title=source["title"], goal=goal,
                           implementation="linked_code" if source["kind"] == "study" else "paper_only",
                           lessons=[]))


def cited_evidence(store: Store, source_id: str, references: list[Evidence]) -> list[dict]:
    source = store.source(source_id)
    members = ([source["metadata"][k] for k in ("paper_id", "repository_id")]
               if source["kind"] == "study" else [source_id])
    chunks = {c["id"]: c for member in members for c in store.chunks(member)}
    evidence = []
    for reference in references:
        chunk = chunks.get(reference.chunk_id)
        if chunk is None or reference.quote not in chunk["text"]:
            raise ValueError("引用必须来自当前材料，摘录必须与原文一致")
        evidence.append(dict(chunk_id=reference.chunk_id, quote=reference.quote,
                             location=chunk["location"], url=chunk["url"], page=chunk.get("page")))
    return evidence


def update(store: Store, session_id: str, action: str, payload) -> dict:
    record = session(store, session_id)
    lessons = record["lessons"]
    if action == "lesson":
        lesson = Lesson.model_validate(payload)
        if lessons and "review" not in lessons[-1] and "skipped" not in lessons[-1]:
            raise ValueError("先完成当前问题的回答与反馈，再进入下一个概念")
        evidence = cited_evidence(store, record["source_id"], lesson.evidence)
        lessons.append(dict(**lesson.model_dump(exclude={"evidence"}), evidence=evidence))
    elif action == "answer":
        answer = str(payload).strip()
        if not 1 <= len(answer) <= 8000:
            raise ValueError("回答需为 1–8000 字符")
        if not lessons or "answer" in lessons[-1] or "skipped" in lessons[-1]:
            raise ValueError("当前没有等待回答的问题")
        lessons[-1]["answer"] = answer
    elif action == "review":
        review = Review.model_validate(payload)
        if not lessons or "answer" not in lessons[-1] or "review" in lessons[-1] or "skipped" in lessons[-1]:
            raise ValueError("先记录当前回答，且同一回答只反馈一次")
        evidence = cited_evidence(store, record["source_id"], review.evidence)
        lessons[-1]["review"] = dict(**review.model_dump(exclude={"evidence"}), evidence=evidence,
                                    provenance="agent assessment; not independently verified")
    elif action == "skip":
        reason = str(payload).strip()
        if not 1 <= len(reason) <= 1000:
            raise ValueError("请记录跳过原因，最多 1000 字符")
        if not lessons or "review" in lessons[-1] or "skipped" in lessons[-1]:
            raise ValueError("没有等待处理的问题")
        lessons[-1]["skipped"] = reason
    else:
        raise ValueError("未知学习操作")
    return save(store, record)


def context(store: Store, session_id: str) -> dict:
    record = session(store, session_id)
    lessons = record["lessons"]
    current = lessons[-1] if lessons else None
    phase = ("ready" if current is None or "review" in current or "skipped" in current else
             "awaiting_feedback" if "answer" in current else "awaiting_answer")
    latest = {}
    for lesson in lessons:
        if "review" in lesson:
            latest[lesson["concept"]] = dict(concept=lesson["concept"], **lesson["review"])
    return dict(session_id=session_id, source_id=record["source_id"], title=record["title"],
                goal=record["goal"], phase=phase, current=current,
                review_queue=[item for item in latest.values() if item["assessment"] != "understood"],
                covered_concepts=list(dict.fromkeys(lesson["concept"] for lesson in lessons)),
                note="学习判断来自 Agent；待复习列表按同名概念最近一次反馈生成，不代表客观测评。")


def markdown(record: dict) -> str:
    lines = [f"# {record['title']}", "", record["goal"], "",
             f"代码状态：{record['implementation']}。反馈由调用方 Agent 提供，不代表独立测评。", ""]
    for index, lesson in enumerate(record["lessons"], 1):
        lines += [f"## {index}. {lesson['concept']}", "", lesson["explanation"], "",
                  "**想一想：** " + lesson["question"], ""]
        if "answer" in lesson:
            lines += ["**我的回答：**", "", lesson["answer"], ""]
        if "review" in lesson:
            review = lesson["review"]
            lines += [f"**反馈（{review['assessment']}）：**", "", review["feedback"], ""]
        if "skipped" in lesson:
            lines += ["**本题跳过：** " + lesson["skipped"], ""]
        if lesson["assumptions"]:
            lines += ["**尚未确认的假设：**", "", *[f"- {a}" for a in lesson["assumptions"]], ""]
        references = lesson["evidence"] + lesson.get("review", {}).get("evidence", [])
        for ref in references:
            lines += [f"> {ref['location']}：{ref['quote']}", ""]
    return "\n".join(lines)
