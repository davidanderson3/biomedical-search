from __future__ import annotations

import gzip
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.code_index import INDEX_SCHEMA, TABLE_SCHEMA
from qe_evidence_vectors.pubtator3 import (
    normalized_pubtator3_relation_type,
    parse_pubtator3_relation_line,
    write_pubtator3_relation_sample,
)


def test_parse_pubtator3_relation_line() -> None:
    relation = parse_pubtator3_relation_line(
        "35378878\tassociate\tChemical|MESH:D003911\tDisease|MESH:D005334\n",
        line_number=7,
    )

    assert relation is not None
    assert relation.pmid == "35378878"
    assert relation.subject.entity_type == "Chemical"
    assert relation.subject.system == "MSH"
    assert relation.subject.identifier == "D003911"
    assert relation.object.entity_type == "Disease"
    assert relation.line_number == 7
    assert normalized_pubtator3_relation_type("positive_correlate") == "associated_with"
    assert normalized_pubtator3_relation_type("cause") == "causes"


def test_write_pubtator3_relation_sample_maps_mesh_to_cui(tmp_path: Path) -> None:
    code_index = tmp_path / "code_index.sqlite"
    conn = sqlite3.connect(code_index)
    conn.executescript(TABLE_SCHEMA)
    conn.executemany(
        """
        INSERT INTO code_mappings(cui, sab, code, scui, sdui, tty, label, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("C0011806", "MSH", "D003911", "", "D003911", "MH", "Dextrans", "Y", "N"),
            ("C0015967", "MSH", "D005334", "", "D005334", "MH", "Fever", "Y", "N"),
        ],
    )
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()

    source = tmp_path / "relation2pubtator3.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write("35378878\tassociate\tChemical|MESH:D003911\tDisease|MESH:D005334\n")

    out = tmp_path / "pubtator3_evidence.jsonl"
    manifest = write_pubtator3_relation_sample(
        source=source,
        out_path=out,
        code_index_path=code_index,
        max_records=10,
    )

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert manifest["records"] == 1
    assert rows[0]["source"] == "pubtator3"
    assert rows[0]["subject_cui"] == "C0011806"
    assert rows[0]["object_cui"] == "C0015967"
    assert rows[0]["relationship_type"] == "associated_with"
    assert rows[0]["edge"]["evidence"]["method"] == "literature_mined"
