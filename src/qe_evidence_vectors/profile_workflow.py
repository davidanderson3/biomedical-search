from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .corpus import merge_corpus_documents
from .label_index import LabelIndex, build_label_index
from .linker import iter_linked_corpus_evidence
from .schema import write_jsonl
from .semantic_profiles import biomedicine_profile_names
from .trie_linker import LabelTrie, iter_linked_corpus_evidence_trie


PROFILE_INDEX_SUFFIX = "profile_multiword_label_index.sqlite"


@dataclass(frozen=True)
class ProfileIndexResult:
    profile: str
    path: Path
    label_count: int


@dataclass(frozen=True)
class ProfileLinkResult:
    profile: str
    index_path: Path
    evidence_path: Path
    evidence_count: int


def safe_profile_name(profile: str) -> str:
    return profile.replace("-", "_")


def default_profiles(profiles: Iterable[str] | None = None) -> list[str]:
    return list(profiles) if profiles else biomedicine_profile_names()


def profile_index_path(
    index_dir: str | Path,
    profile: str,
    *,
    prefix: str = "umls",
    suffix: str = PROFILE_INDEX_SUFFIX,
) -> Path:
    return Path(index_dir).expanduser() / f"{prefix}_{safe_profile_name(profile)}_{suffix}"


def profile_evidence_path(
    out_dir: str | Path,
    profile: str,
    *,
    run_name: str = "corpus",
) -> Path:
    return Path(out_dir).expanduser() / f"{run_name}_{safe_profile_name(profile)}_evidence.jsonl"


def build_profile_indexes(
    *,
    mrconso_path: str | Path,
    mrsty_path: str | Path,
    out_dir: str | Path,
    profiles: Iterable[str] | None = None,
    prefix: str = "umls",
    language: str = "ENG",
    include_suppressed: bool = False,
    include_generic: bool = False,
    min_chars: int = 3,
    min_tokens: int = 2,
    max_tokens: int = 8,
    replace: bool = False,
) -> list[ProfileIndexResult]:
    results = []
    for profile in default_profiles(profiles):
        out_path = profile_index_path(out_dir, profile, prefix=prefix)
        count = build_label_index(
            mrconso_path=mrconso_path,
            out_path=out_path,
            mrsty_path=mrsty_path,
            semantic_profiles=[profile],
            language=language,
            include_suppressed=include_suppressed,
            include_generic=include_generic,
            min_chars=min_chars,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            replace=replace,
        )
        results.append(ProfileIndexResult(profile=profile, path=out_path, label_count=count))
    return results


def link_profile_shards(
    *,
    corpus_paths: list[str | Path],
    index_dir: str | Path,
    out_dir: str | Path,
    profiles: Iterable[str] | None = None,
    index_prefix: str = "umls",
    index_suffix: str = PROFILE_INDEX_SUFFIX,
    run_name: str = "corpus",
    max_label_tokens: int = 8,
    context_chars: int = 320,
    max_ambiguity: int = 1,
    max_mentions_per_cui: int = 8,
    max_docs: int | None = None,
    materialize_corpus: bool = False,
    matcher: str = "trie",
    tag_evidence: bool = True,
) -> list[ProfileLinkResult]:
    results = []
    materialized_documents = None
    if materialize_corpus:
        documents = merge_corpus_documents(corpus_paths)
        if max_docs is not None:
            documents = itertools.islice(documents, max_docs)
        materialized_documents = list(documents)
    for profile in default_profiles(profiles):
        index_path = profile_index_path(
            index_dir,
            profile,
            prefix=index_prefix,
            suffix=index_suffix,
        )
        if not index_path.exists():
            raise FileNotFoundError(f"missing label index for profile {profile}: {index_path}")
        out_path = profile_evidence_path(out_dir, profile, run_name=run_name)
        if materialized_documents is None:
            documents = merge_corpus_documents(corpus_paths)
            if max_docs is not None:
                documents = itertools.islice(documents, max_docs)
        else:
            documents = iter(materialized_documents)
        kwargs = {
            "max_label_tokens": max_label_tokens,
            "context_chars": context_chars,
            "max_ambiguity": max_ambiguity,
            "max_mentions_per_cui": max_mentions_per_cui,
            "evidence_tag": safe_profile_name(profile) if tag_evidence else "",
        }
        if matcher == "trie":
            trie = LabelTrie.from_sqlite(index_path, max_label_tokens=max_label_tokens)
            evidence = iter_linked_corpus_evidence_trie(documents, trie, **kwargs)
            count = write_jsonl(out_path, evidence)
        elif matcher == "sqlite":
            with LabelIndex(index_path) as index:
                evidence = iter_linked_corpus_evidence(documents, index, **kwargs)
                count = write_jsonl(out_path, evidence)
        else:
            raise ValueError(f"unknown matcher: {matcher}")
        results.append(
            ProfileLinkResult(
                profile=profile,
                index_path=index_path,
                evidence_path=out_path,
                evidence_count=count,
            )
        )
    return results
