from __future__ import annotations

import threading
from pathlib import Path

from qe_evidence_vectors.label_index import LabelIndex
from qe_evidence_vectors.text import normalized_key


class LabelFallback:
    ALLOW_SHORT_SINGLE_TOKENS = {
        "a1c",
        "bnp",
        "braf",
        "brca1",
        "brca2",
        "ct",
        "ecg",
        "egd",
        "egfr",
        "hdl",
        "her2",
        "hiv",
        "inr",
        "ldl",
        "mri",
        "pcr",
        "phq",
        "psa",
        "t3",
        "t4",
        "tsh",
    }
    SKIP_SINGLE_TOKENS = {
        "after",
        "before",
        "controlled",
        "disease",
        "exam",
        "examination",
        "high",
        "poorly",
        "diagnostic",
        "evaluation",
        "history",
        "monitoring",
        "patient",
        "person",
        "physical",
        "place",
        "possible",
        "procedure",
        "regular",
        "return",
        "risk",
        "scheduling",
        "several",
        "significant",
        "studies",
        "sudden",
        "surgical",
        "symptoms",
        "time",
        "with",
        "worsen",
        "found",
        "given",
        "grew",
        "heavy",
        "initial",
        "later",
        "missing",
        "missed",
        "ordered",
        "planned",
        "prompted",
        "raised",
        "receive",
        "received",
        "recommended",
        "reviewed",
        "showed",
        "shown",
        "started",
        "supported",
        "treated",
        "triggered",
    }
    SKIP_SPANS = {
        "clinical procedure",
        "medical procedure",
        "no evidence of",
        "patient advised to",
        "surgical procedure",
        "surgical procedures",
    }

    def __init__(self, paths: list[Path], *, max_tokens: int = 8, rows_per_span: int = 50) -> None:
        self.paths = [path for path in paths if path.exists()]
        self._local = threading.local()
        self.max_tokens = max_tokens
        self.rows_per_span = rows_per_span

    def indexes(self) -> list[LabelIndex]:
        indexes = getattr(self._local, "indexes", None)
        if indexes is None:
            indexes = [LabelIndex(path) for path in self.paths]
            self._local.indexes = indexes
        return indexes

    def search(self, query: str, *, limit: int) -> list[dict]:
        tokens = normalized_key(query).split()
        if not tokens:
            return []
        query_content_tokens = max(self.content_token_count(tokens), 1)
        best: dict[str, dict] = {}
        for span_norm, token_count, span_content_tokens in self.query_spans(tokens):
            rows = []
            for index in self.indexes():
                rows.extend(index.lookup(span_norm, limit=self.rows_per_span))
            if not rows:
                continue
            unique_cuis = {row["cui"] for row in rows}
            for row in rows:
                score = self.label_score(
                    token_count=token_count,
                    query_content_tokens=query_content_tokens,
                    span_content_tokens=span_content_tokens,
                    unique_cui_count=len(unique_cuis),
                    is_preferred=str(row["ispref"]) == "Y",
                )
                candidate = {
                    "doc_id": f"{row['cui']}:umls_label",
                    "cui": row["cui"],
                    "view": "umls_label",
                    "score": score,
                    "labels": [row["label"]],
                    "sources": ["umls_label"],
                    "evidence_count": 0,
                    "match_type": "umls_label",
                    "matched_label": row["label"],
                    "matched_query_span": span_norm,
                    "matched_sab": row["sab"],
                    "matched_tty": row["tty"],
                    "matched_ispref": row["ispref"],
                    "text": (
                        f"CUI: {row['cui']}\n"
                        "Evidence view: umls_label\n"
                        "UMLS label fallback:\n"
                        f"- {row['label']}\n"
                        f"Matched query span: {span_norm}"
                    ),
                    "evidence_items": [],
                }
                current = best.get(row["cui"])
                if current is None or candidate["score"] > current["score"]:
                    best[row["cui"]] = candidate
        return sorted(best.values(), key=lambda item: item["score"], reverse=True)[:limit]

    def query_spans(self, tokens: list[str]):
        max_len = min(self.max_tokens, len(tokens))
        seen = set()
        for length in range(max_len, 0, -1):
            for start in range(0, len(tokens) - length + 1):
                span_tokens = tokens[start : start + length]
                if length == 1:
                    token = span_tokens[0]
                    if (
                        token in self.SKIP_SINGLE_TOKENS
                        or (len(token) < 5 and token not in self.ALLOW_SHORT_SINGLE_TOKENS)
                    ):
                        continue
                span = " ".join(span_tokens)
                if span in self.SKIP_SPANS:
                    continue
                if span in seen:
                    continue
                seen.add(span)
                content_count = self.content_token_count(span_tokens)
                if content_count <= 0:
                    continue
                yield span, length, content_count

    def content_token_count(self, tokens: list[str]) -> int:
        return sum(1 for token in tokens if token not in self.SKIP_SINGLE_TOKENS)

    @staticmethod
    def label_score(
        *,
        token_count: int,
        query_content_tokens: int,
        span_content_tokens: int,
        unique_cui_count: int,
        is_preferred: bool,
    ) -> float:
        coverage = span_content_tokens / max(query_content_tokens, 1)
        rarity = 0.15 if unique_cui_count <= 3 else (-0.15 if unique_cui_count >= 20 else 0.0)
        preferred = 0.02 if is_preferred else 0.0
        if span_content_tokens >= query_content_tokens:
            return 1.05 + (0.12 * min(token_count, 5)) + rarity + preferred
        if span_content_tokens == 1:
            return 0.68 + (0.15 * coverage) + (0.30 * rarity) + preferred
        return 0.78 + (0.35 * coverage) + (0.04 * min(token_count, 4)) + rarity + preferred
