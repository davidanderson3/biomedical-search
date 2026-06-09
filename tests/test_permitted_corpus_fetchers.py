from __future__ import annotations

import csv
import io
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.fetchers import (  # noqa: E402
    BookshelfOAEntry,
    bookshelf_oa_archive_to_documents,
    clinicaltrials_study_to_document,
    dailymed_spl_to_document,
    fetch_bookshelf_oa_documents,
    fetch_obo_ontology_documents,
    fetch_reference_page_documents,
    html_page_to_text,
    medlineplus_genetics_summary_to_document,
    medlineplus_topic_to_document,
    obo_text_to_terms,
    ontology_source_policies,
    read_dailymed_setids_from_mrsat,
    reference_source_policies,
    reference_source_policy,
)


def _tar_gz_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            payload = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_clinicaltrials_study_to_document_keeps_conditions_interventions_and_population() -> None:
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT00000001",
                "briefTitle": "Osimertinib for EGFR-mutated non-small cell lung cancer",
                "officialTitle": "A trial of osimertinib in EGFR mutated NSCLC",
            },
            "descriptionModule": {
                "briefSummary": "Participants have brain metastases and receive targeted therapy.",
            },
            "conditionsModule": {
                "conditions": ["Non-Small Cell Lung Cancer", "Brain Metastases"],
            },
            "armsInterventionsModule": {
                "interventions": [
                    {"type": "Drug", "name": "Osimertinib", "description": "EGFR tyrosine kinase inhibitor"}
                ],
            },
            "eligibilityModule": {
                "sex": "ALL",
                "minimumAge": "18 Years",
                "maximumAge": "99 Years",
                "eligibilityCriteria": "EGFR mutation required.",
            },
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE3"]},
            "statusModule": {"overallStatus": "RECRUITING"},
        }
    }

    document = clinicaltrials_study_to_document(study, query="lung cancer")

    assert document is not None
    assert document.doc_id == "NCT:NCT00000001"
    assert document.source == "clinicaltrials_gov"
    assert "Non-Small Cell Lung Cancer" in document.text
    assert "Osimertinib" in document.text
    assert "EGFR mutation required" in document.text
    assert document.metadata["conditions"] == ["Non-Small Cell Lung Cancer", "Brain Metastases"]
    assert document.metadata["interventions"] == ["Osimertinib"]


def test_clinicaltrials_outcomes_only_keeps_posted_result_text() -> None:
    study = {
        "hasResults": True,
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT00000002",
                "briefTitle": "Diabetic foot ulcer treatment trial",
            },
            "descriptionModule": {
                "briefSummary": "This protocol summary should not be indexed as outcome evidence.",
            },
            "conditionsModule": {"conditions": ["Diabetic Foot"]},
            "armsInterventionsModule": {
                "interventions": [
                    {"type": "Drug", "name": "Gentamicin Sponge", "description": "Protocol intervention text"}
                ],
            },
            "eligibilityModule": {"eligibilityCriteria": "Protocol eligibility should be omitted."},
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
            "statusModule": {"overallStatus": "COMPLETED"},
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "Planned wound healing endpoint"}],
            },
        },
        "resultsSection": {
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "type": "PRIMARY",
                        "title": "Number of Participants With Clinical Cure",
                        "description": "Clinical cure at final visit.",
                        "reportingStatus": "POSTED",
                        "paramType": "COUNT_OF_PARTICIPANTS",
                        "unitOfMeasure": "Participants",
                        "timeFrame": "Day 21",
                        "groups": [
                            {"id": "OG000", "title": "Gentamicin Sponge"},
                            {"id": "OG001", "title": "Levofloxacin"},
                        ],
                        "denoms": [
                            {
                                "units": "Participants",
                                "counts": [
                                    {"groupId": "OG000", "value": "34"},
                                    {"groupId": "OG001", "value": "15"},
                                ],
                            }
                        ],
                        "classes": [
                            {
                                "categories": [
                                    {
                                        "measurements": [
                                            {"groupId": "OG000", "value": "14"},
                                            {"groupId": "OG001", "value": "7"},
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        },
    }

    document = clinicaltrials_study_to_document(study, query="diabetes", outcomes_only=True)

    assert document is not None
    assert "ClinicalTrials.gov posted outcome results" in document.text
    assert "Number of Participants With Clinical Cure" in document.text
    assert "Gentamicin Sponge: 14" in document.text
    assert "Protocol eligibility should be omitted" not in document.text
    assert "This protocol summary should not be indexed" not in document.text
    assert document.metadata["evidence_mode"] == "outcomes_only"
    assert document.metadata["has_results"] is True
    assert document.metadata["posted_outcome_result_count"] == 1
    assert document.metadata["posted_primary_outcome_result_count"] == 1


def test_clinicaltrials_require_results_skips_protocol_only_study() -> None:
    study = {
        "hasResults": False,
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000003", "briefTitle": "Protocol only"},
            "descriptionModule": {"briefSummary": "Protocol text."},
            "outcomesModule": {"primaryOutcomes": [{"measure": "Planned endpoint"}]},
        },
    }

    assert clinicaltrials_study_to_document(study, require_results=True) is None
    assert clinicaltrials_study_to_document(study, outcomes_only=True) is None


def test_medlineplus_topic_to_document_keeps_lay_synonyms_and_groups() -> None:
    topic = ET.fromstring(
        """
        <health-topic id="42" language="English" title="Migraine" url="https://medlineplus.gov/migraine.html">
          <also-called>Migraine headache</also-called>
          <see-reference>Headache</see-reference>
          <group>Brain and Nerves</group>
          <mesh-heading><descriptor>Migraine Disorders</descriptor></mesh-heading>
          <full-summary><p>Migraine is a recurring type of headache.</p></full-summary>
        </health-topic>
        """
    )

    document = medlineplus_topic_to_document(topic, source_url="https://example.test/topics.zip")

    assert document is not None
    assert document.doc_id == "MEDLINEPLUS:42"
    assert document.source == "medlineplus"
    assert "Migraine headache" in document.text
    assert "Brain and Nerves" in document.text
    assert document.metadata["also_called"] == ["Migraine headache"]
    assert document.metadata["mesh_headings"] == ["Migraine Disorders"]


def test_medlineplus_topic_to_document_strips_escaped_summary_markup() -> None:
    topic = ET.fromstring(
        """
        <health-topic id="43" language="English" title="A1C">
          <full-summary>&lt;p&gt;A1C is a blood test for &lt;a href="https://example.test"&gt;type 2 diabetes&lt;/a&gt;.&lt;/p&gt;</full-summary>
        </health-topic>
        """
    )

    document = medlineplus_topic_to_document(topic)

    assert document is not None
    assert "A1C is a blood test for type 2 diabetes." in document.text
    assert "<p>" not in document.text
    assert "<a " not in document.text


def test_medlineplus_topic_to_document_skips_spanish_by_default() -> None:
    topic = ET.fromstring('<health-topic id="es1" language="Spanish" title="Diabetes" />')

    assert medlineplus_topic_to_document(topic) is None
    assert medlineplus_topic_to_document(topic, include_spanish=True) is not None


def test_dailymed_spl_to_document_keeps_relevant_label_sections() -> None:
    root = ET.fromstring(
        """
        <document>
          <title>PANTOPRAZOLE SODIUM tablet</title>
          <component>
            <structuredBody>
              <component>
                <section>
                  <title>INDICATIONS AND USAGE</title>
                  <text><paragraph>Pantoprazole is indicated for erosive esophagitis.</paragraph></text>
                </section>
              </component>
              <component>
                <section>
                  <title>ADVERSE REACTIONS</title>
                  <text><paragraph>Headache and diarrhea were reported.</paragraph></text>
                </section>
              </component>
            </structuredBody>
          </component>
        </document>
        """
    )

    document = dailymed_spl_to_document(
        root,
        setid="11111111-2222-3333-4444-555555555555",
        drug_name="pantoprazole",
    )

    assert document is not None
    assert document.doc_id == "DAILYMED:11111111-2222-3333-4444-555555555555"
    assert document.source == "dailymed"
    assert "erosive esophagitis" in document.text
    assert "diarrhea" in document.text
    assert document.metadata["setid"] == "11111111-2222-3333-4444-555555555555"


def test_medlineplus_genetics_gene_summary_to_document_keeps_related_conditions() -> None:
    summary = ET.fromstring(
        """
        <gene-summary id="21929">
          <gene-symbol>AAAS</gene-symbol>
          <name>aladin WD repeat nucleoporin</name>
          <ghr-page>https://medlineplus.gov/genetics/gene/aaas</ghr-page>
          <text-list>
            <text>
              <text-role>function</text-role>
              <html><p>The AAAS gene provides instructions for making ALADIN.</p></html>
            </text>
          </text-list>
          <related-health-condition-list>
            <related-health-condition><name>Triple A syndrome</name></related-health-condition>
          </related-health-condition-list>
          <synonym-list><synonym>ALADIN</synonym></synonym-list>
          <db-key-list><db-key><db>NCBI Gene</db><key>8086</key></db-key></db-key-list>
        </gene-summary>
        """
    )

    document = medlineplus_genetics_summary_to_document(summary)

    assert document is not None
    assert document.doc_id == "MEDLINEPLUS_GENETICS:gene:21929"
    assert document.source == "medlineplus_genetics"
    assert "Triple A syndrome" in document.text
    assert "ALADIN" in document.text
    assert document.metadata["db_keys"] == ["NCBI Gene:8086"]


def test_medlineplus_genetics_summary_text_preserves_paragraph_spacing() -> None:
    summary = ET.fromstring(
        """
        <health-condition-summary id="1">
          <name>Example syndrome</name>
          <text-list>
            <text>
              <html><p>First sentence.</p><p>Second sentence.</p></html>
            </text>
          </text-list>
        </health-condition-summary>
        """
    )

    document = medlineplus_genetics_summary_to_document(summary)

    assert document is not None
    assert "First sentence. Second sentence." in document.text


def test_obo_text_to_terms_keeps_synonyms_xrefs_and_relationships() -> None:
    header, terms = obo_text_to_terms(
        """
        format-version: 1.2
        data-version: hp/releases/2026-05-01
        ontology: hp

        [Term]
        id: HP:0001250
        name: Seizure
        namespace: phenotypic_abnormality
        def: "A seizure is an intermittent abnormality of nervous system physiology." [HPO:probinson]
        synonym: "Epileptic seizure" EXACT []
        xref: UMLS:C0036572
        is_a: HP:0012638 ! Abnormal nervous system physiology
        relationship: part_of HP:0000707 ! Abnormality of nervous system

        [Term]
        id: HP:9999999
        name: Old phenotype
        is_obsolete: true
        """
    )

    assert header["data-version"] == "hp/releases/2026-05-01"
    assert len(terms) == 2
    assert terms[0].term_id == "HP:0001250"
    assert terms[0].name == "Seizure"
    assert terms[0].definition.startswith("A seizure")
    assert terms[0].synonyms == ("Epileptic seizure",)
    assert terms[0].xrefs == ("UMLS:C0036572",)
    assert terms[0].parents == ("HP:0012638",)
    assert terms[0].relationships == ("part_of HP:0000707",)
    assert terms[1].is_obsolete is True


def test_fetch_obo_ontology_documents_uses_local_source_and_skips_obsolete_by_default(tmp_path: Path) -> None:
    obo_path = tmp_path / "hp.obo"
    obo_path.write_text(
        """
        format-version: 1.2
        data-version: hp/releases/2026-05-01
        ontology: hp

        [Term]
        id: BFO:0000001
        name: entity

        [Term]
        id: HP:0001250
        name: Seizure
        namespace: phenotypic_abnormality
        def: "A seizure is an intermittent abnormality of nervous system physiology." [HPO:probinson]
        synonym: "Epileptic seizure" EXACT []
        xref: UMLS:C0036572

        [Term]
        id: HP:9999999
        name: Old phenotype
        is_obsolete: true
        """,
        encoding="utf-8",
    )

    documents = list(fetch_obo_ontology_documents("hpo", source_url=str(obo_path)))
    with_obsolete = list(fetch_obo_ontology_documents("hpo", source_url=str(obo_path), include_obsolete=True))

    assert [document.doc_id for document in documents] == ["HPO:HP_0001250"]
    assert documents[0].source == "hpo"
    assert "Epileptic seizure" in documents[0].text
    assert documents[0].metadata["data_version"] == "hp/releases/2026-05-01"
    assert documents[0].metadata["license_status"] == "public_reusable_with_attribution_no_modification"
    assert len(with_obsolete) == 2


def test_read_dailymed_setids_from_mrsat_extracts_unique_values(tmp_path: Path) -> None:
    path = tmp_path / "MRSAT.RRF"
    path.write_text(
        "\n".join(
            [
                "C1|L1|S1|A1|CODE|X|ATUI|SATUI|SPL_SET_ID|MTHSPL|11111111-2222-3333-4444-555555555555|N|",
                "C1|L1|S1|A1|CODE|X|ATUI|SATUI|SPL_SET_ID|MTHSPL|11111111-2222-3333-4444-555555555555|N|",
                "C2|L2|S2|A2|CODE|X|ATUI|SATUI|OTHER|MTHSPL|22222222-3333-4444-5555-666666666666|N|",
                "C3|L3|S3|A3|CODE|X|ATUI|SATUI|DAILYMED_SETID|MTHSPL|33333333-4444-5555-6666-777777777777|N|",
            ]
        ),
        encoding="utf-8",
    )

    assert read_dailymed_setids_from_mrsat(path) == [
        "11111111-2222-3333-4444-555555555555",
        "33333333-4444-5555-6666-777777777777",
    ]


def test_bookshelf_oa_archive_to_documents_skips_toc_and_keeps_license() -> None:
    entry = BookshelfOAEntry(
        archive_path="aa/bb/asthma_NBK1.tar.gz",
        title="Expert Panel Report: Guidelines for the Diagnosis and Management of Asthma",
        publisher="National Heart, Lung, and Blood Institute (US)",
        publication_year="2026",
        accession_id="NBK1",
        last_updated="2026-05-13 00:00:00",
    )
    payload = _tar_gz_bytes(
        {
            "asthma_NBK1/license.txt": "Public-domain source with attribution requested.",
            "asthma_NBK1/TOC.nxml": """
                <book-part book-part-type="toc">
                  <book-meta><book-title-group><book-title>Asthma</book-title></book-title-group></book-meta>
                  <book-part-meta><title-group><title>Table of Contents</title></title-group></book-part-meta>
                  <body><p>Contents</p></body>
                </book-part>
            """,
            "asthma_NBK1/ch1.nxml": """
                <book-part book-part-type="chapter" id="ch1">
                  <book-meta>
                    <book-title-group><book-title>Asthma Guidelines</book-title></book-title-group>
                    <abstract><p>Clinical guidance for asthma diagnosis and treatment.</p></abstract>
                  </book-meta>
                  <book-part-meta><title-group><title>Diagnosis</title></title-group></book-part-meta>
                  <body><sec><title>Evaluation</title><p>Diagnosis includes symptoms, spirometry, differential diagnosis, severity assessment, and treatment planning for persistent asthma in primary care.</p></sec></body>
                </book-part>
            """,
        }
    )

    documents = list(
        bookshelf_oa_archive_to_documents(
            payload,
            entry=entry,
            package_url="https://ftp.ncbi.nlm.nih.gov/pub/litarch/aa/bb/asthma_NBK1.tar.gz",
            min_chars=50,
        )
    )

    assert len(documents) == 1
    assert documents[0].source == "ncbi_bookshelf_oa"
    assert documents[0].title == "Diagnosis"
    assert "spirometry" in documents[0].text
    assert documents[0].metadata["license_status"] == "nlm_litarch_open_access_subset"
    assert "Public-domain source" in documents[0].metadata["source_license"]


def test_fetch_bookshelf_oa_documents_uses_local_file_list_and_package_base(tmp_path: Path) -> None:
    package_path = tmp_path / "aa" / "bb" / "asthma_NBK1.tar.gz"
    package_path.parent.mkdir(parents=True)
    package_path.write_bytes(
        _tar_gz_bytes(
            {
                "asthma_NBK1/license.txt": "Read the package license before reuse.",
                "asthma_NBK1/ch1.nxml": """
                    <book-part book-part-type="chapter" id="ch1">
                      <book-meta><book-title-group><book-title>Asthma Guidelines</book-title></book-title-group></book-meta>
                      <book-part-meta><title-group><title>Assessment</title></title-group></book-part-meta>
                      <body><p>Asthma assessment includes history, examination, triggers, lung function testing, differential diagnosis, and stepwise management.</p></body>
                    </book-part>
                """,
            }
        )
    )
    file_list = tmp_path / "file_list.csv"
    file_list.write_text(
        "\n".join(
            [
                "File,Title,Publisher,Publication Year,Accession ID,Last Updated (YYYY-MM-DD HH:MM:SS)",
                "aa/bb/asthma_NBK1.tar.gz,Expert Panel Report: Guidelines for Asthma,National Heart Lung and Blood Institute,2026,NBK1,2026-05-13 00:00:00",
            ]
        ),
        encoding="utf-8",
    )

    documents = list(
        fetch_bookshelf_oa_documents(
            file_list_url=str(file_list),
            package_base_url=str(tmp_path),
            terms=["asthma"],
            max_books=1,
            max_records=5,
            min_chars=50,
        )
    )

    assert len(documents) == 1
    assert documents[0].metadata["archive_path"] == "aa/bb/asthma_NBK1.tar.gz"
    assert documents[0].metadata["retrieved_via"] == "nlm_litarch_ftp_open_access_subset"


def test_reference_page_html_to_text_removes_scripts_and_keeps_title() -> None:
    title, text = html_page_to_text(
        b"""
        <html>
          <head><title>Ignored browser title</title><script>secret()</script></head>
          <body><h1>Night Sweats</h1><p>Differential diagnosis includes infection and malignancy.</p></body>
        </html>
        """
    )

    assert title == "Night Sweats"
    assert "Differential diagnosis includes infection and malignancy." in text
    assert "secret" not in text


def test_fetch_reference_page_documents_tracks_license_policy_and_local_html(tmp_path: Path) -> None:
    page = tmp_path / "nci.html"
    page.write_text(
        "<html><body><h1>Colorectal Cancer Diagnosis</h1><p>Diagnosis may include colonoscopy and biopsy.</p></body></html>",
        encoding="utf-8",
    )

    documents = list(fetch_reference_page_documents("nci", urls=[str(page)], max_records=1))

    assert len(documents) == 1
    assert documents[0].source == "nci"
    assert "colonoscopy and biopsy" in documents[0].text
    assert documents[0].metadata["license_status"] == "public_reusable"
    assert documents[0].metadata["terms_url"] == reference_source_policy("nci")["terms_url"]


def test_fetch_reference_page_documents_blocks_permission_required_sources(tmp_path: Path) -> None:
    restricted_sources = [
        "merck_manual_professional",
        "msd_manual_professional",
        "aafp",
        "medscape",
        "bmj_best_practice",
        "nice_cks",
        "ncbi_bookshelf_statpearls",
        "patient_info_professional",
        "gpnotebook",
        "wikem",
    ]
    for source in restricted_sources:
        page = tmp_path / f"{source}.html"
        page.write_text("<html><body><h1>Lymphadenopathy</h1></body></html>", encoding="utf-8")

        try:
            list(fetch_reference_page_documents(source, urls=[str(page)], max_records=1))
        except ValueError as exc:
            assert str(reference_source_policy(source)["fetch_policy"]) in str(exc)
        else:
            raise AssertionError(f"{source} should not be fetched without explicit licensed-source opt-in")


def test_reference_source_policy_config_tracks_fetcher_sources() -> None:
    with (ROOT / "config" / "reference_source_policy.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    config_sources = {row["source"] for row in rows}
    assert set(reference_source_policies()).issubset(config_sources)
    assert "ncbi_bookshelf_oa" in config_sources
    assert {"hpo", "mondo"}.issubset(config_sources)
    assert {"hpo", "mondo"}.issubset(ontology_source_policies())
