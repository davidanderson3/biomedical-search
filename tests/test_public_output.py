from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.code_index import CodeIndex, INDEX_SCHEMA, TABLE_SCHEMA
from qe_evidence_vectors.public_output import PublicOutputMixin


class DummyPublicOutput(PublicOutputMixin):
    def __init__(self, code_index: CodeIndex, public_sources: tuple[str, ...] = ("MSH", "NCI")) -> None:
        self.code_index = code_index
        self.public_output_only = True
        self.public_output_sources = public_sources
        self.public_label_cache = {}

    def best_record_for_cui(self, cui: str):  # pragma: no cover - only used for NEW concepts
        return None


def write_code_index(path: Path) -> CodeIndex:
    conn = sqlite3.connect(path)
    conn.executescript(TABLE_SCHEMA)
    conn.executemany(
        """
        INSERT INTO preferred_terms(cui, label, sab, code, tty, suppress)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("C0000001", "Restricted preferred name", "SNOMEDCT_US", "111", "PT", "N"),
            ("C0000001", "Safe display name", "MSH", "D000001", "MH", "N"),
            ("C0000002", "Safe related name", "NCI", "NCI0002", "PT", "N"),
            ("C0000003", "Restricted only name", "SNOMEDCT_US", "333", "PT", "N"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO code_mappings(cui, sab, code, scui, sdui, tty, label, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("C0000001", "SNOMEDCT_US", "111", "111", "", "PT", "Restricted synonym", "Y", "N"),
            ("C0000001", "MSH", "D000001", "", "D000001", "MH", "Safe display name", "Y", "N"),
            ("C0000002", "NCI", "NCI0002", "NCI0002", "", "PT", "Safe related name", "Y", "N"),
            ("C0000003", "SNOMEDCT_US", "333", "333", "", "PT", "Restricted only name", "Y", "N"),
        ],
    )
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return CodeIndex(path)


def test_public_output_replaces_restricted_preferred_name_and_drops_source_payload(
    tmp_path: Path,
) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted preferred name",
                "labels": ["Restricted preferred name", "Restricted synonym"],
                "codes": [{"system": "SNOMEDCT_US", "code": "111", "label": "Restricted synonym"}],
                "source_asserted_codes": [
                    {"system": "SNOMEDCT_US", "code": "111", "label": "Restricted synonym"}
                ],
                "mappings": [{"sab": "SNOMEDCT_US", "code": "111", "label": "Restricted synonym"}],
                "definitions": [
                    {
                        "cui": "C0000001",
                        "source": "SNOMEDCT_US",
                        "definition": "Restricted definition",
                        "rank": 1,
                    },
                    {
                        "cui": "C0000001",
                        "source": "NCI",
                        "definition": "Safe definition",
                        "rank": 2,
                    },
                ],
                "related_concepts": [
                    {
                        "cui": "C0000002",
                        "source": "MSH",
                        "relation": "RO",
                        "label": "Restricted relation label",
                    },
                    {
                        "cui": "C0000003",
                        "source": "SNOMEDCT_US",
                        "relation": "RO",
                        "label": "Restricted only name",
                    },
                ],
                "matched_label": "Restricted synonym",
                "matched_sab": "SNOMEDCT_US",
                "mrrel_signal_reasons": [{"source": "SNOMEDCT_US"}],
                "score_breakdown": {
                    "mrrel_signal_reasons": [{"source": "SNOMEDCT_US"}],
                    "vector_component": 0.5,
                },
                "text": "UMLS labels:\n- Restricted preferred name",
            }
        ],
        "semantic_result_buckets": [
            {
                "key": "clinical_findings",
                "label": "Clinical Findings",
                "codes": ["OBS"],
                "hits": 1,
            }
        ],
    }

    cleaned = output.public_output_payload(payload)

    assert cleaned["hits"][0]["name"] == "Safe display name"
    assert cleaned["hits"][0]["labels"] == ["Safe display name"]
    assert "codes" not in cleaned["hits"][0]
    assert "source_asserted_codes" not in cleaned["hits"][0]
    assert "mappings" not in cleaned["hits"][0]
    assert "matched_label" not in cleaned["hits"][0]
    assert "matched_sab" not in cleaned["hits"][0]
    assert "mrrel_signal_reasons" not in cleaned["hits"][0]
    assert "score_breakdown" not in cleaned["hits"][0]
    assert "text" not in cleaned["hits"][0]
    assert all("codes" not in bucket for bucket in cleaned["semantic_result_buckets"])
    assert cleaned["hits"][0]["definitions"] == [
        {
            "cui": "C0000001",
            "source": "NCI",
            "definition": "Safe definition",
            "rank": 2,
        }
    ]
    assert cleaned["hits"][0]["related_concepts"] == [
        {
            "cui": "C0000002",
            "source": "MSH",
            "relation": "RO",
            "label": "Safe related name",
        }
    ]
    assert "Restricted" not in str(cleaned)
    assert "SNOMEDCT_US" not in str(cleaned)


def test_public_output_drops_hits_without_allowed_display_label(tmp_path: Path) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000003",
                "name": "Restricted only name",
                "labels": ["Restricted only name"],
                "score": 1.0,
            }
        ]
    }

    assert output.public_output_payload(payload)["hits"] == []


def test_public_output_keeps_allowed_strict_source_code_rows(tmp_path: Path) -> None:
    output = DummyPublicOutput(
        write_code_index(tmp_path / "codes.sqlite"),
        public_sources=("MSH", "NCI", "RXNORM"),
    )
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "metformin",
                "view": "source_code",
                "sources": ["source_code", "RXNORM"],
                "source_code_result": True,
                "match_type": "source_code_label",
                "score": 1.4,
                "rank_score": 1.4,
                "codes": [
                    {
                        "system": "RXNORM",
                        "system_name": "RxNorm",
                        "sab": "RXNORM",
                        "code": "6809",
                        "source_asserted_code": "6809",
                        "source_cui": "6809",
                        "source_dui": "",
                        "scui": "6809",
                        "sdui": "",
                        "tty": "IN",
                        "label": "metformin",
                        "ispref": "Y",
                    }
                ],
                "source_asserted_codes": [
                    {
                        "system": "RXNORM",
                        "system_name": "RxNorm",
                        "sab": "RXNORM",
                        "code": "6809",
                        "source_asserted_code": "6809",
                        "label": "metformin",
                        "tty": "IN",
                    }
                ],
                "mappings": [{"sab": "RXNORM", "code": "6809", "label": "metformin"}],
                "matched_label": "metformin",
            }
        ]
    }

    cleaned = output.public_output_payload(payload)

    assert cleaned["hits"][0]["name"] == "metformin"
    assert cleaned["hits"][0]["sources"] == ["source_code", "RXNORM"]
    assert cleaned["hits"][0]["codes"] == cleaned["hits"][0]["source_asserted_codes"]
    assert cleaned["hits"][0]["codes"][0]["system"] == "RXNORM"
    assert cleaned["hits"][0]["codes"][0]["code"] == "6809"
    assert cleaned["hits"][0]["source_code_result"] is True
    assert "mappings" not in cleaned["hits"][0]
    assert "matched_label" not in cleaned["hits"][0]


def test_public_output_drops_disallowed_strict_source_code_rows(tmp_path: Path) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted synonym",
                "view": "source_code",
                "sources": ["source_code", "SNOMEDCT_US"],
                "source_code_result": True,
                "codes": [
                    {
                        "system": "SNOMEDCT_US",
                        "code": "111",
                        "label": "Restricted synonym",
                        "tty": "PT",
                    }
                ],
                "source_asserted_codes": [
                    {
                        "system": "SNOMEDCT_US",
                        "code": "111",
                        "label": "Restricted synonym",
                        "tty": "PT",
                    }
                ],
            }
        ]
    }

    assert output.public_output_payload(payload)["hits"] == []


def test_public_output_keeps_direct_code_resolver_hit_without_restricted_code_rows(
    tmp_path: Path,
) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted synonym",
                "view": "pmc_oa_clinical_context",
                "sources": ["code", "pmc_oa"],
                "match_type": "code",
                "matched_input": "111",
                "matched_code_input": "111",
                "score": 1.2,
                "rank_score": 1.2,
                "codes": [
                    {
                        "system": "SNOMEDCT_US",
                        "code": "111",
                        "label": "Restricted synonym",
                        "tty": "PT",
                    }
                ],
                "source_asserted_codes": [
                    {
                        "system": "SNOMEDCT_US",
                        "code": "111",
                        "label": "Restricted synonym",
                        "tty": "PT",
                    }
                ],
            }
        ]
    }

    cleaned = output.public_output_payload(payload)

    assert cleaned["hits"][0]["name"] == "Safe display name"
    assert cleaned["hits"][0]["sources"] == ["pmc_oa"]
    assert cleaned["hits"][0]["match_type"] == "code"
    assert cleaned["hits"][0]["matched_code_input"] == "111"
    assert "codes" not in cleaned["hits"][0]
    assert "source_asserted_codes" not in cleaned["hits"][0]
    assert "SNOMEDCT_US" not in str(cleaned)


def test_public_output_keeps_active_label_supplement_new_hit(tmp_path: Path) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "NEW3560835",
                "name": "bibasilar crackles",
                "labels": ["bibasilar crackles"],
                "matched_label": "bibasilar crackles",
                "sources": ["active_label_supplement"],
                "score": 1.0,
            }
        ]
    }

    cleaned = output.public_output_payload(payload)

    assert cleaned["hits"] == [
        {
            "cui": "NEW3560835",
            "name": "bibasilar crackles",
            "labels": ["bibasilar crackles"],
            "sources": ["active_label_supplement"],
            "score": 1.0,
            "label": "bibasilar crackles",
        }
    ]


def test_public_output_keeps_active_label_supplement_existing_cui_without_public_label(
    tmp_path: Path,
) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C4049341",
                "name": "supratherapeutic INR",
                "labels": ["supratherapeutic INR"],
                "matched_label": "supratherapeutic INR",
                "sources": ["active_label_supplement"],
                "score": 1.0,
            }
        ]
    }

    cleaned = output.public_output_payload(payload)

    assert cleaned["hits"][0]["cui"] == "C4049341"
    assert cleaned["hits"][0]["name"] == "supratherapeutic INR"
    assert cleaned["hits"][0]["labels"] == ["supratherapeutic INR"]
    assert cleaned["hits"][0]["sources"] == ["active_label_supplement"]


def test_public_output_strips_internal_definition_source_from_active_label_hit(
    tmp_path: Path,
) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted preferred name",
                "labels": ["Restricted preferred name", "blood thinner"],
                "sources": ["active_label_supplement", "pmc_oa", "umls_definition"],
                "score": 1.44,
                "matched_definition": {
                    "cui": "C0000001",
                    "source": "MEDLINEPLUS",
                    "definition": "<h3>Internal ranking snippet</h3>",
                },
            }
        ]
    }

    cleaned = output.public_output_payload(payload)

    assert len(cleaned["hits"]) == 1
    assert cleaned["hits"][0]["sources"] == ["active_label_supplement", "pmc_oa"]
    assert cleaned["hits"][0]["name"] == "Safe display name"
    assert "matched_definition" not in cleaned["hits"][0]


def test_public_output_drops_hits_from_unapproved_evidence_sources(tmp_path: Path) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted preferred name",
                "labels": ["Restricted preferred name"],
                "sources": ["pubmed", "restricted_private"],
                "evidence_items": [
                    {
                        "text": "Restricted evidence text",
                        "sources": [{"source": "restricted_private"}],
                    }
                ],
            },
            {
                "cui": "C0000001",
                "name": "Restricted preferred name",
                "labels": ["Restricted preferred name"],
                "sources": ["pubmed"],
                "evidence_items": [
                    {
                        "text": "Public evidence text",
                        "sources": [{"source": "pubmed"}],
                    }
                ],
            },
        ]
    }

    cleaned = output.public_output_payload(payload)

    assert len(cleaned["hits"]) == 1
    assert cleaned["hits"][0]["sources"] == ["pubmed"]
    assert "evidence_items" not in cleaned["hits"][0]
    assert "Restricted" not in str(cleaned)


def test_public_output_preserves_non_response_hits_counts(tmp_path: Path) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted preferred name",
                "labels": ["Restricted preferred name"],
            }
        ],
        "source_contribution": {
            "items": [
                {
                    "source": "pubmed",
                    "hits": 1,
                }
            ]
        },
    }

    cleaned = output.public_output_payload(payload)

    assert cleaned["hits"][0]["name"] == "Safe display name"
    assert cleaned["source_contribution"]["items"][0]["hits"] == 1


def test_public_output_preserves_scalar_relation_named_summary_counts(tmp_path: Path) -> None:
    output = DummyPublicOutput(write_code_index(tmp_path / "codes.sqlite"))
    payload = {
        "hits": [
            {
                "cui": "C0000001",
                "name": "Restricted preferred name",
                "labels": ["Restricted preferred name"],
            }
        ],
        "source_contribution": {
            "items": [
                {
                    "source": "pubmed",
                    "related_concepts": 2.0,
                    "definitions": 1,
                }
            ]
        },
    }

    cleaned = output.public_output_payload(payload)

    summary = cleaned["source_contribution"]["items"][0]
    assert summary["related_concepts"] == 2.0
    assert summary["definitions"] == 1
