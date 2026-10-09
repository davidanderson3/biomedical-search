from __future__ import annotations

import sqlite3

from qe_evidence_vectors.descendant_expansion import traverse_descendants
from qe_evidence_vectors.elastic_runtime_indexes import ElasticRelationIndex
from qe_evidence_vectors.relation_index import INDEX_SCHEMA, TABLE_SCHEMA, RelationIndex
from qe_evidence_vectors.search_quality_http import OPENAPI_SPEC
from qe_evidence_vectors.search_execution import SearchExecutionMixin
from qe_evidence_vectors.search_ranking import rank_hits


class GraphRelationIndex:
    def __init__(self, graph: dict[str, list[str]]) -> None:
        self.graph = graph
        self.calls: list[list[str]] = []

    def lookup_children_many(self, cuis, *, limit_per_parent: int = 100):
        parents = list(cuis)
        self.calls.append(parents)
        return {
            parent: [
                {
                    "parent_cui": parent,
                    "child_cui": child,
                    "cui": child,
                    "relation": "PAR",
                    "rela": "inverse_isa",
                    "source": "SNOMEDCT_US",
                    "direction": "incoming",
                    "label": child,
                }
                for child in self.graph.get(parent, [])[:limit_per_parent]
            ]
            for parent in parents
        }


def test_descendant_traversal_is_breadth_first_and_cycle_safe() -> None:
    index = GraphRelationIndex(
        {
            "C0000001": ["C0000002", "C0000003"],
            "C0000002": ["C0000004"],
            "C0000003": ["C0000004"],
            "C0000004": ["C0000001"],
        }
    )

    result = traverse_descendants(index, ["C0000001"], max_depth=3, limit=20)

    assert [row["cui"] for row in result["candidates"]] == [
        "C0000002",
        "C0000003",
        "C0000004",
    ]
    assert [row["depth"] for row in result["candidates"]] == [1, 1, 2]
    assert result["candidates"][2]["path"] == ["C0000001", "C0000002", "C0000004"]
    assert result["cycle_skips"] == 2
    assert result["visited_count"] == 4
    assert index.calls == [["C0000001"], ["C0000002", "C0000003"], ["C0000004"]]


def test_relation_index_uses_mrrel_par_chd_direction_to_find_children(tmp_path) -> None:
    path = tmp_path / "relations.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(TABLE_SCHEMA)
    connection.executemany(
        """
        INSERT INTO related_concepts(
            source_cui, target_cui, relation, rela, rui, sab, direction, label, rank
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("C0000001", "C0000002", "PAR", "inverse_isa", "R1", "SNOMEDCT_US", "incoming", "Child two", 1),
            ("C0000001", "C0000003", "CHD", "", "R2", "MSH", "outgoing", "Child three", 2),
            ("C0000001", "C0000004", "PAR", "inverse_isa", "R3", "SNOMEDCT_US", "outgoing", "Parent", 3),
            ("C0000001", "C0000005", "CHD", "", "R4", "MSH", "incoming", "Parent", 4),
        ],
    )
    connection.executescript(INDEX_SCHEMA)
    connection.commit()
    connection.close()

    index = RelationIndex(path)
    children = index.lookup_children("C0000001")
    index.close()

    assert [row["cui"] for row in children] == ["C0000002", "C0000003"]
    assert children[0]["parent_cui"] == "C0000001"
    assert children[0]["source"] == "SNOMEDCT_US"


class FakeElasticRelationStore:
    def __init__(self) -> None:
        self.index = "relations"
        self.body = None

    def search(self, body):
        self.body = body
        return {
            "aggregations": {
                "parents": {
                    "buckets": [
                        {
                            "key": "C0000001",
                            "children": {
                                "hits": {
                                    "hits": [
                                        {
                                            "_source": {
                                                "source_cui": "C0000001",
                                                "target_cui": "C0000002",
                                                "relation": "PAR",
                                                "rela": "inverse_isa",
                                                "sab": "SNOMEDCT_US",
                                                "direction": "incoming",
                                                "label": "Child two",
                                                "rank": 1,
                                            }
                                        }
                                    ]
                                }
                            },
                        }
                    ]
                }
            }
        }


def test_elastic_relation_index_batches_descendant_frontier() -> None:
    store = FakeElasticRelationStore()
    index = ElasticRelationIndex(store)

    result = index.lookup_children_many(["C0000001", "C0000009"], limit_per_parent=12)

    assert result["C0000001"][0]["cui"] == "C0000002"
    assert result["C0000009"] == []
    assert store.body["size"] == 0
    assert store.body["aggs"]["parents"]["aggs"]["children"]["top_hits"]["size"] == 12


def test_descendant_rank_signal_is_bounded_and_explainable() -> None:
    direct = {
        "cui": "C0000001",
        "name": "Diabetes mellitus",
        "labels": ["Diabetes mellitus"],
        "score": 1.2,
        "match_type": "umls_label",
        "matched_query_span": "diabetes mellitus",
        "evidence_count": 0,
        "semantic_types": [],
    }
    descendant = {
        "cui": "C0000002",
        "name": "Type 1 diabetes mellitus",
        "labels": ["Type 1 diabetes mellitus"],
        "score": 0.72,
        "match_type": "umls_descendant",
        "descendant_expansion_component": 0.28,
        "descendant_expansion": {
            "seed_cui": "C0000001",
            "parent_cui": "C0000001",
            "depth": 1,
            "path": ["C0000001", "C0000002"],
        },
        "evidence_count": 0,
        "semantic_types": [],
    }

    ranked = rank_hits("diabetes mellitus", [descendant, direct], top_k=10)
    by_cui = {hit["cui"]: hit for hit in ranked}

    assert ranked[0]["cui"] == "C0000001"
    assert by_cui["C0000002"]["score_breakdown"]["descendant_expansion_component"] == 0.28
    assert by_cui["C0000002"]["score_breakdown"]["retrieval_kind"] == "umls_descendant"


def test_descendant_merge_preserves_the_complete_baseline_pool() -> None:
    service = SearchExecutionMixin()
    baseline = [
        {
            "cui": "C0000001",
            "name": "Diabetes mellitus",
            "labels": ["Diabetes mellitus"],
            "score": 1.2,
            "match_type": "umls_label",
            "matched_query_span": "diabetes mellitus",
            "evidence_count": 1,
            "semantic_types": [],
        },
        {
            "cui": "C0000002",
            "name": "metformin",
            "labels": ["metformin"],
            "score": 1.1,
            "match_type": "umls_label",
            "matched_query_span": "metformin",
            "evidence_count": 1,
            "semantic_types": [],
        },
    ]
    descendants = [
        {
            "cui": f"C{index:07d}",
            "name": f"Diabetes subtype {index}",
            "labels": [f"Diabetes subtype {index}"],
            "score": 0.72,
            "match_type": "umls_descendant",
            "descendant_expansion_component": 0.28,
            "descendant_expansion": {"depth": 1},
            "evidence_count": 0,
            "semantic_types": [],
        }
        for index in range(3, 8)
    ]

    merged = service.merge_descendant_expansion_hits(
        "diabetes mellitus metformin",
        baseline,
        descendants,
        top_k=2,
    )

    assert {"C0000001", "C0000002"} <= {hit["cui"] for hit in merged}
    assert len(merged) > 2


class PublicDescendantHarness(SearchExecutionMixin):
    def __init__(self) -> None:
        self.relation_index = GraphRelationIndex(
            {"C0000001": ["C0000002", "C0000003"]}
        )

    def candidate_from_cui(self, cui, **_kwargs):
        return {"cui": cui, "name": cui, "labels": [cui], "score": 0.72}

    def hit_from_candidate(self, candidate):
        return dict(candidate)

    def public_output_enabled(self):
        return True

    def _public_output_hit(self, hit):
        return None if hit["cui"] == "C0000002" else dict(hit)


def test_descendants_that_cannot_be_returned_do_not_enter_public_ranking() -> None:
    service = PublicDescendantHarness()

    hits, metadata = service.descendant_expansion_hits(
        "diabetes",
        {"candidates": [{"cui": "C0000001"}]},
        enabled=True,
        max_depth=1,
        limit=20,
    )

    assert [hit["cui"] for hit in hits] == ["C0000003"]
    assert metadata["public_output_filtered_count"] == 1
    assert metadata["returned_candidate_count"] == 1


def test_openapi_documents_descendant_expansion_parameters() -> None:
    parameters = OPENAPI_SPEC["paths"]["/api/search"]["get"]["parameters"]
    names = {parameter["name"] for parameter in parameters}
    assert {"descendants", "descendant_depth", "descendant_limit"} <= names
