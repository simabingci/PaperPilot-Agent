"""CPU sparse-vector RAG: reproducible character hashing, not semantic embeddings."""

from sklearn.feature_extraction.text import HashingVectorizer

from paperpilot.store import Store


def search(store: Store, source_id: str, query: str, limit: int = 5, path: str | None = None) -> list[dict]:
    chunks = [c for c in store.chunks(source_id) if path is None or c.get("path") == path]
    if not chunks:
        return []
    vectorizer = HashingVectorizer(analyzer="char", ngram_range=(2, 4), n_features=2**18,
                                  alternate_sign=False, norm="l2", lowercase=True)
    matrix = vectorizer.transform(c["text"] for c in chunks)
    scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
    ranking = scores.argsort()[::-1][:limit]
    return [dict(chunks[i], score=round(float(scores[i]), 4)) for i in ranking if scores[i] >= 0.015]
