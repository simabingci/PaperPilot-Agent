"""Bilingual query expansion: let a Chinese question reach an English paper.

The retriever is character-based and monolingual in practice: a Chinese question
shares almost no n-grams with English text. Expansion adds an English keyword query
built from a small, explicit ML/CS glossary. It is deterministic, offline and
inspectable — no model call, no hidden translation service.
"""

import re

CJK = re.compile(r"[\u4e00-\u9fff]")

# Longest terms first so "数据集划分" is not shadowed by "数据集".
TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("数据集划分", ("dataset split",)),
    ("批大小", ("batch size",)),
    ("学习率", ("learning rate",)),
    ("优化器", ("optimizer", "adam", "sgd")),
    ("超参数", ("hyperparameter", "batch size", "learning rate")),
    ("数据集", ("dataset",)),
    ("预处理", ("preprocessing",)),
    ("正则化", ("regularization",)),
    ("注意力", ("attention",)),
    ("卷积", ("convolution", "dilated")),
    ("循环", ("recurrent", "lstm")),
    ("网络", ("network", "architecture")),
    ("分割", ("segmentation",)),
    ("检测", ("detection",)),
    ("隐写", ("steganography", "steganalysis")),
    ("摔倒", ("fall detection",)),
    ("雷达", ("radar",)),
    ("关键点", ("keypoint", "pose")),
    ("训练", ("training",)),
    ("评估", ("evaluation", "evaluate")),
    ("损失", ("loss",)),
    ("准确率", ("accuracy",)),
    ("精确率", ("precision",)),
    ("召回率", ("recall",)),
    ("容差", ("tolerance",)),
    ("划分", ("split",)),
    ("模型", ("model",)),
    ("方法", ("method", "approach")),
    ("实验", ("experiment",)),
    ("结果", ("results",)),
    ("复现", ("reproduction", "reproduce")),
    ("论文", ("paper",)),
    ("表格", ("table",)),
    ("公式", ("equation", "formula")),
    ("基线", ("baseline",)),
    ("消融", ("ablation",)),
    ("特征", ("feature",)),
)

MAX_TERMS = 12


def is_chinese(text: str) -> bool:
    return bool(CJK.search(text))


def expand_query(query: str) -> list[str]:
    """Return the original query, plus an English keyword query when Chinese terms match.

    The original is always first: expansion can only add candidates, never replace the
    caller's words. Unknown Chinese terms simply produce no expansion.
    """
    if not is_chinese(query):
        return [query]
    terms: list[str] = []
    for chinese, english in TERMS:
        if chinese in query:
            terms.extend(term for term in english if term not in terms)
    if not terms:
        return [query]
    return [query, " ".join(terms[:MAX_TERMS])]