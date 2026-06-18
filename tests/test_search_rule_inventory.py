from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_search_rule_inventory.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("build_search_rule_inventory", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rule_inventory_renders_markdown_and_html_summary() -> None:
    module = load_script_module()
    inventory = module.build_inventory()
    totals = module.inventory_totals(inventory)

    markdown = module.render_markdown(inventory)
    html = module.render_html(inventory)

    assert totals["active_heuristic_items"] >= 600
    assert "## Inventory Summary" in markdown
    assert f"Active heuristic items in the live search path: {totals['active_heuristic_items']}" in markdown
    assert html.startswith("<!doctype html>")
    assert "<title>Search Rule Inventory</title>" in html
    assert "Active heuristic items" in html
    assert f"<strong>{totals['active_heuristic_items']:,}</strong>" in html


def test_rule_inventory_cli_writes_html_and_json_by_default(tmp_path: Path, monkeypatch) -> None:
    module = load_script_module()
    html_path = tmp_path / "inventory.html"
    json_path = tmp_path / "inventory.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_search_rule_inventory.py",
            "--html-output",
            str(html_path),
            "--json-output",
            str(json_path),
        ],
    )

    assert module.main() == 0
    assert html_path.exists()
    assert json_path.exists()
    assert "Search Rule Inventory" in html_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["rule_classes"]


def test_rule_inventory_cli_writes_markdown_only_when_requested(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_script_module()
    md_path = tmp_path / "inventory.md"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_search_rule_inventory.py",
            "--output",
            str(md_path),
            "--no-html-output",
        ],
    )

    assert module.main() == 0
    assert md_path.exists()
    assert "Search Rule Inventory" in md_path.read_text(encoding="utf-8")
