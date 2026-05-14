from __future__ import annotations

import re
import unicodedata


def ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def normalized_key(text: str) -> str:
    text = ascii_fold(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def feature_tokens(text: str) -> list[str]:
    normalized = normalized_key(text)
    tokens = normalized.split()
    features = list(tokens)
    compact = "".join(tokens)
    for size in (3, 4):
        if len(compact) >= size:
            features.extend(compact[i : i + size] for i in range(len(compact) - size + 1))
    return features
