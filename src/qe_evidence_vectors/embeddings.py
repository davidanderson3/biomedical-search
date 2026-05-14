from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Protocol

from .compat import silence_urllib3_libressl_warning
from .schema import ConceptDocument, VectorRecord
from .text import feature_tokens

DEFAULT_BIOMEDICAL_BERT_MODEL = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"

class Embedder(Protocol):
    provider_name: str
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    provider_name = "hashing"

    def __init__(self, dim: int = 384) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim
        self.model_name = f"signed-token-char-hashing-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for feature in feature_tokens(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "big")
            index = number % self.dim
            sign = 1.0 if (number >> 63) == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


@dataclass(frozen=True)
class HashingIdfWeights:
    doc_count: int
    weights: dict[str, float]
    default_idf: float
    formula: str = "log((1 + n_docs) / (1 + df)) + 1"


def build_hashing_idf_weights(texts: Iterable[str]) -> HashingIdfWeights:
    doc_freq: Counter[str] = Counter()
    doc_count = 0
    for text in texts:
        features = set(feature_tokens(text))
        if not features:
            continue
        doc_count += 1
        doc_freq.update(features)
    if doc_count <= 0:
        return HashingIdfWeights(doc_count=0, weights={}, default_idf=1.0)
    weights = {
        feature: math.log((1.0 + doc_count) / (1.0 + df)) + 1.0
        for feature, df in doc_freq.items()
    }
    default_idf = math.log(1.0 + doc_count) + 1.0
    return HashingIdfWeights(
        doc_count=doc_count,
        weights=weights,
        default_idf=default_idf,
    )


def write_hashing_idf_weights(path: str | Path, weights: HashingIdfWeights) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "doc_count": weights.doc_count,
        "default_idf": weights.default_idf,
        "formula": weights.formula,
        "weights": weights.weights,
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_hashing_idf_weights(path: str | Path) -> HashingIdfWeights:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    raw_weights = payload.get("weights") or {}
    if not isinstance(raw_weights, dict):
        raise ValueError(f"invalid hashing IDF weights file: {path}")
    return HashingIdfWeights(
        doc_count=int(payload.get("doc_count") or 0),
        weights={str(key): float(value) for key, value in raw_weights.items()},
        default_idf=float(payload.get("default_idf") or 1.0),
        formula=str(payload.get("formula") or "log((1 + n_docs) / (1 + df)) + 1"),
    )


class IdfHashingEmbedder:
    provider_name = "hashing-idf"

    def __init__(
        self,
        *,
        dim: int = 384,
        idf_weights: HashingIdfWeights,
        idf_path: str | Path | None = None,
    ) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim
        self.idf_weights = idf_weights
        self.idf_path = str(idf_path or "")
        self.model_name = f"signed-token-char-hashing-idf-{dim}"
        self.metadata = {
            "hashing_idf_doc_count": idf_weights.doc_count,
            "hashing_idf_formula": idf_weights.formula,
        }
        if self.idf_path:
            self.metadata["hashing_idf_path"] = self.idf_path

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        counts = Counter(feature_tokens(text))
        for feature, count in counts.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "big")
            index = number % self.dim
            sign = 1.0 if (number >> 63) == 0 else -1.0
            tf = 1.0 + math.log(float(count))
            idf = self.idf_weights.weights.get(feature, self.idf_weights.default_idf)
            vector[index] += sign * tf * idf
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


class SentenceTransformersEmbedder:
    provider_name = "sentence-transformers"

    def __init__(
        self,
        model_name: str,
        *,
        local_files_only: bool = False,
        max_seq_length: int | None = None,
    ) -> None:
        silence_urllib3_libressl_warning()
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Install it or use --provider hashing."
            ) from exc
        self.model_name = model_name
        try:
            self.model = SentenceTransformer(model_name, local_files_only=local_files_only)
        except TypeError:
            if local_files_only:
                raise RuntimeError(
                    "the installed sentence-transformers package does not support local_files_only"
                )
            self.model = SentenceTransformer(model_name)
        if max_seq_length is not None:
            if max_seq_length <= 0:
                raise ValueError("max_seq_length must be positive")
            self.model.max_seq_length = max_seq_length

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            convert_to_numpy=False,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]


class TransformersClsEmbedder:
    provider_name = "transformers-cls"

    def __init__(
        self,
        model_name: str = DEFAULT_BIOMEDICAL_BERT_MODEL,
        *,
        local_files_only: bool = False,
        max_seq_length: int | None = None,
        device: str | None = None,
    ) -> None:
        silence_urllib3_libressl_warning()
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "torch and transformers are required for --provider transformers-cls"
            ) from exc
        if max_seq_length is not None and max_seq_length <= 0:
            raise ValueError("max_seq_length must be positive")
        self.torch = torch
        self.model_name = model_name
        self.max_seq_length = max_seq_length
        self.device = self._resolve_device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        self.model = AutoModel.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        self.model.to(self.device)
        self.model.eval()
        self.metadata = {
            "embedding_pooling": "cls",
            "embedding_device": str(self.device),
        }

    def _resolve_device(self, requested: str | None):
        torch = self.torch
        if requested and requested != "auto":
            return torch.device(requested)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        torch = self.torch
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_seq_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model(**encoded)
            vectors = output.last_hidden_state[:, 0, :]
            vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
        return vectors.detach().cpu().tolist()


def make_embedder(
    provider: str,
    *,
    model: str | None = None,
    dim: int = 384,
    idf_path: str | Path | None = None,
    local_files_only: bool = False,
    max_seq_length: int | None = None,
    device: str | None = None,
) -> Embedder:
    if provider == "hashing":
        return HashingEmbedder(dim=dim)
    if provider == "hashing-idf":
        if not idf_path:
            raise ValueError("--idf-path is required for --provider hashing-idf")
        return IdfHashingEmbedder(
            dim=dim,
            idf_weights=load_hashing_idf_weights(idf_path),
            idf_path=idf_path,
        )
    if provider == "sentence-transformers":
        if not model:
            raise ValueError("--model is required for sentence-transformers")
        return SentenceTransformersEmbedder(
            model,
            local_files_only=local_files_only,
            max_seq_length=max_seq_length,
        )
    if provider in {"transformers-cls", "bert-cls", "sapbert"}:
        return TransformersClsEmbedder(
            model or DEFAULT_BIOMEDICAL_BERT_MODEL,
            local_files_only=local_files_only,
            max_seq_length=max_seq_length,
            device=device,
        )
    raise ValueError(f"unknown provider: {provider}")


def embed_documents(
    documents: Iterable[ConceptDocument],
    embedder: Embedder,
    *,
    batch_size: int = 64,
    include_document_metadata: bool = False,
    vector_precision: int | None = 6,
    omit_text: bool = False,
) -> list[VectorRecord]:
    return list(
        iter_embed_documents(
            documents,
            embedder,
            batch_size=batch_size,
            include_document_metadata=include_document_metadata,
            vector_precision=vector_precision,
            omit_text=omit_text,
        )
    )


def iter_embed_documents(
    documents: Iterable[ConceptDocument],
    embedder: Embedder,
    *,
    batch_size: int = 64,
    include_document_metadata: bool = False,
    vector_precision: int | None = 6,
    omit_text: bool = False,
) -> Iterator[VectorRecord]:
    batch: list[ConceptDocument] = []
    for record in documents:
        batch.append(record)
        if len(batch) >= batch_size:
            yield from _embed_batch(
                batch,
                embedder,
                include_document_metadata=include_document_metadata,
                vector_precision=vector_precision,
                omit_text=omit_text,
            )
            batch.clear()
    if batch:
        yield from _embed_batch(
            batch,
            embedder,
            include_document_metadata=include_document_metadata,
            vector_precision=vector_precision,
            omit_text=omit_text,
        )


def _embed_batch(
    batch: list[ConceptDocument],
    embedder: Embedder,
    *,
    include_document_metadata: bool,
    vector_precision: int | None,
    omit_text: bool,
) -> Iterator[VectorRecord]:
    if not batch:
        return
    vectors = embedder.embed([record.text for record in batch])
    for record, vector in zip(batch, vectors):
        if vector_precision is not None:
            vector = [round(value, vector_precision) for value in vector]
        metadata = {
            "embedding_provider": embedder.provider_name,
            "embedding_model": embedder.model_name,
            "evidence_count": record.evidence_count,
            "sources": record.sources,
            "labels": record.labels,
        }
        metadata.update(getattr(embedder, "metadata", {}))
        if include_document_metadata:
            metadata["document_metadata"] = record.metadata
        yield VectorRecord(
            doc_id=record.doc_id,
            cui=record.cui,
            view=record.view,
            vector=vector,
            text="" if omit_text else record.text,
            metadata=metadata,
        )
