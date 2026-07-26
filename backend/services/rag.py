from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Species


def tokenize(text: str) -> list[str]:
    text = text.lower()
    latin = re.findall(r"[a-z0-9]+", text)
    chinese = [char for char in text if "\u4e00" <= char <= "\u9fff"]
    words = [token for token in re.split(r"[\s，。；：、,.!?()（）/]+", text) if len(token) > 1]
    return latin + chinese + words


@dataclass
class RAGDocument:
    species_id: int
    title: str
    content: str


class SpeciesRAG:
    """A dependency-light BM25-style retrieval index over the seeded species knowledge base.

    Chroma/vector retrieval is available as an optional project extra, while this local index keeps
    the core website functional on machines without a GPU or embedding service.
    """

    def __init__(self, db: Session):
        species = db.scalars(select(Species).order_by(Species.id)).all()
        self.documents = [
            RAGDocument(
                species_id=item.id,
                title=f"{item.common_name}（{item.scientific_name}）",
                content=(
                    f"中文名：{item.common_name}。学名：{item.scientific_name}。"
                    f"分类：{item.category}。保护级别：{item.protection_level}。"
                    f"栖息地：{item.habitat}。分布：{item.distribution}。"
                    f"特征：{item.traits}。食性：{item.diet}。活动规律：{item.activity}。"
                    f"生态价值：{item.ecology_value}。主要威胁：{item.threats}。"
                    f"保护建议：{item.conservation}。趣味知识：{'；'.join(item.facts)}"
                ),
            )
            for item in species
        ]
        self.tokens = [tokenize(doc.title + " " + doc.content) for doc in self.documents]
        self.doc_freq: Counter[str] = Counter()
        for tokens in self.tokens:
            self.doc_freq.update(set(tokens))

    def _score(self, query_tokens: list[str], index: int) -> float:
        tokens = self.tokens[index]
        if not tokens or not query_tokens:
            return 0.0
        tf = Counter(tokens)
        length_norm = 1.0 + 0.015 * len(tokens)
        n_docs = max(1, len(self.documents))
        score = 0.0
        for token in query_tokens:
            frequency = tf.get(token, 0)
            if not frequency:
                continue
            idf = math.log((n_docs + 1) / (self.doc_freq.get(token, 0) + 0.5)) + 1.0
            score += idf * (frequency / (frequency + 1.2 * length_norm))
        return score

    def search(self, query: str, limit: int = 4, species_id: int | None = None) -> list[dict]:
        if not self.documents:
            return []
        if species_id:
            return [doc.__dict__ for doc in self.documents if doc.species_id == species_id][:limit]
        query_tokens = tokenize(query)
        ranked = sorted(
            ((doc, self._score(query_tokens, index)) for index, doc in enumerate(self.documents)),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            {"species_id": doc.species_id, "title": doc.title, "content": doc.content, "score": round(score, 5)}
            for doc, score in ranked[:limit]
            if score > 0
        ]
