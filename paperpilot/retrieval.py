"""CPU sparse-vector RAG: reproducible character hashing, not semantic embeddings."""

from collections import OrderedDict

from sklearn.feature_extraction.text import HashingVectorizer

from paperpilot.expansion import expand_query
from paperpilot.store import Store

MIN_SCORE = 0.015
VECTORIZER = HashingVectorizer(analyzer="char", ngram_range=(2, 4), n_features=2**18,
                               alternate_sign=False, norm="l2", lowercase=True)
_CACHE_LIMIT = 4
# (source_id, chunk count, last chunk id) -> (chunks, matrix); ingests only append.
_INDEX_CACHE: OrderedDict[tuple[str, int, str], tuple[list[dict], object]] = OrderedDict()


def _index(store: Store, source_id: str) -> tuple[list[dict], object]:
    chunks = store.chunks(source_id)
    key = (source_id, len(chunks), chunks[-1]["id"] if chunks else "")
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        _INDEX_CACHE.move_to_end(key)
        return cached
    matrix = VECTORIZER.transform([chunk["text"] for chunk in chunks]) if chunks else None
    _INDEX_CACHE[key] = (chunks, matrix)
    _INDEX_CACHE.move_to_end(key)
    while len(_INDEX_CACHE) > _CACHE_LIMIT:
        _INDEX_CACHE.popitem(last=False)
    return chunks, matrix


def clear_cache() -> None:
    _INDEX_CACHE.clear()


def search(store: Store, source_id: str, query: str, limit: int = 5, path: str | None = None) -> list[dict]:
    chunks, matrix = _index(store, source_id)
    if not chunks:
        return []
    scores = (matrix @ VECTORIZER.transform([query]).T).toarray().ravel()
    results = []
    for index in scores.argsort()[::-1]:
        if scores[index] < MIN_SCORE:
            break
        chunk = chunks[index]
        if path is not None and chunk.get("path") != path:
            continue
        results.append(dict(chunk, score=round(float(scores[index]), 4)))
        if len(results) >= limit:
            break
    return results


def search_multi(store: Store, source_id: str, query: str, limit: int = 5,
                 path: str | None = None) -> tuple[list[dict], list[str]]:
    """Search the caller's query plus its bilingual expansion, merged by best score.

    Returns the hits and the extra query variants that were actually used, so a caller
    can tell whether an English expansion contributed evidence.
    """
    variants = expand_query(query)
    merged: dict[str, dict] = {}
    for variant in variants:
        for item in search(store, source_id, variant, limit=limit, path=path):
            existing = merged.get(item["id"])
            if existing is None or item["score"] > existing["score"]:
                merged[item["id"]] = dict(item, matched_query=variant)
    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    return ranked[:limit], variants[1:]