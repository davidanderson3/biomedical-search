from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_search_quality_coverage_audit.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("build_search_quality_coverage_audit", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_semantic_index(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE semantic_types (
            cui TEXT NOT NULL,
            tui TEXT NOT NULL,
            stn TEXT NOT NULL,
            sty TEXT NOT NULL,
            atui TEXT NOT NULL,
            PRIMARY KEY (cui, tui, atui)
        ) WITHOUT ROWID
        """
    )
    conn.executemany(
        "INSERT INTO semantic_types(cui, tui, stn, sty, atui) VALUES (?, ?, ?, ?, ?)",
        [
            ("C0018801", "T047", "B2.2.1.2.1", "Disease or Syndrome", "AT1"),
            ("C0004238", "T047", "B2.2.1.2.1", "Disease or Syndrome", "AT2"),
            ("C0000005", "T121", "A1.4.1.1.1", "Pharmacologic Substance", "AT3"),
        ],
    )
    conn.commit()
    conn.close()


def write_label_index(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE labels (
            norm TEXT NOT NULL,
            cui TEXT NOT NULL,
            label TEXT NOT NULL,
            sab TEXT NOT NULL,
            tty TEXT NOT NULL,
            ispref TEXT NOT NULL,
            suppress TEXT NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO labels(norm, cui, label, sab, tty, ispref, suppress) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("heart failure", "C0018801", "Heart failure", "TEST", "PT", "Y", "N"),
            ("atrial fibrillation", "C0004238", "Atrial Fibrillation", "TEST", "PT", "Y", "N"),
            ("drug noise", "C0000005", "Drug noise", "TEST", "PT", "Y", "N"),
        ],
    )
    conn.commit()
    conn.close()


def test_split_cuis_accepts_pipe_and_comma_lists() -> None:
    module = load_script_module()

    assert module.split_cuis("C0018801| C0004238,NEW1234567 |") == [
        "C0018801",
        "C0004238",
        "NEW1234567",
    ]


def test_build_audit_counts_targets_risks_and_groups(tmp_path: Path) -> None:
    module = load_script_module()
    source = tmp_path / "queries.tsv"
    source.write_text(
        "\n".join(
            [
                "id\tquery\texpected_cuis\tdisallowed_cuis",
                "q1\theart failure and atrial fibrillation\tC0018801|C0004238\tC0000005",
                "q2\tdrug mention 1\tC0000005\t",
                "q3\tdrug mention 2\tC0000005\t",
                "q4\tdrug mention 3\tC0000005\t",
                "",
            ]
        ),
        encoding="utf-8",
    )
    semantic_index = tmp_path / "semantic.sqlite"
    label_index = tmp_path / "labels.sqlite"
    out_dir = tmp_path / "coverage"
    write_semantic_index(semantic_index)
    write_label_index(label_index)

    summary = module.build_audit(
        source_files=[source],
        semantic_type_index=semantic_index,
        label_index=label_index,
        out_dir=out_dir,
    )

    assert summary["unique_target_cuis"] == 3
    assert summary["target_mentions"] == 5
    assert summary["unique_risk_cuis"] == 1
    assert summary["largest_group"] == "CHEM"
    groups = {row["semantic_group"]: row for row in summary["group_rows"]}
    assert groups["DISO"]["unique_target_cuis"] == 2
    assert groups["CHEM"]["unique_target_cuis"] == 1
    assert groups["CHEM"]["unique_risk_cuis"] == 1
    concepts = list(csv.DictReader((out_dir / "coverage_concepts.tsv").open(), delimiter="\t"))
    labels_by_cui = {row["cui"]: row["label"] for row in concepts}
    assert labels_by_cui["C0018801"] == "Heart failure"
    assert labels_by_cui["C0000005"] == "Drug noise"
    saved = json.loads((out_dir / "coverage_summary.json").read_text(encoding="utf-8"))
    assert saved["unique_target_cuis"] == 3
    assert saved["largest_group"] == "CHEM"
