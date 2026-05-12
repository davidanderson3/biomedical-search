#!/bin/sh
set -eu

PORT="${PORT:-8766}"
ELASTIC_URL="${ELASTIC_URL:-http://localhost:9200}"
ELASTIC_INDEX="${ELASTIC_INDEX:-qe-scaling-sapbert-cls}"

VECTOR_PATHS=""
DOC_PATHS=""

add_vector() {
  if [ -f "$1" ]; then
    VECTOR_PATHS="${VECTOR_PATHS} $1"
  fi
}

add_doc() {
  if [ -f "$1" ]; then
    DOC_PATHS="${DOC_PATHS} $1"
  fi
}

add_vector build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_002_common_clinical_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_003_abbreviation_language_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_004_drug_safety_therapeutics_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_005_diagnostics_procedures_devices_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_baseline_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_next2_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1331_1330_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1329_1328_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1327_1326_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1325_1324_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1323_1322_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1321_1320_concept_vectors.sapbert_cls.jsonl

add_doc build/scaling_chunk_001_gap_topics_concept_documents.jsonl
add_doc build/scaling_chunk_002_common_clinical_concept_documents.jsonl
add_doc build/scaling_chunk_003_abbreviation_language_concept_documents.jsonl
add_doc build/scaling_chunk_004_drug_safety_therapeutics_concept_documents.jsonl
add_doc build/scaling_chunk_005_diagnostics_procedures_devices_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_baseline_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_next2_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1331_1330_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1329_1328_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1327_1326_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1325_1324_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1323_1322_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1321_1320_concept_documents.jsonl

exec python3 scripts/search_quality_server.py \
  --port "$PORT" \
  --vectors $VECTOR_PATHS \
  --docs $DOC_PATHS \
  --evidence \
  --provenance-index build/search_quality_provenance.sqlite \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --elastic-url "$ELASTIC_URL" \
  --elastic-index "$ELASTIC_INDEX" \
  --elastic-num-candidates 300 \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --code-index build/cui_code_index.sqlite \
  --relation-index build/umls_related_concepts.sqlite \
  --progress-plan config/pubmed_bulk_recent_1321_1320.plan.json \
  --judgments-out build/scaling_runs/pubmed_bulk_recent_1321_1320/search_quality_judgments.csv \
  "$@"
