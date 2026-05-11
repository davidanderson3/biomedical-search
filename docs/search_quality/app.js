    const state = {
      status: null,
      lastQuery: "",
      lastResults: [],
      lastSemanticViews: [],
      lastSemanticViewSources: [],
      lastSemanticGroupViews: [],
      lastSemanticResultBuckets: [],
      lastRelatedResultBuckets: [],
      lastScoring: null,
      includeRelated: false,
      selectedSemanticBucketKeys: [],
      searchRequestSeq: 0,
      searchAbortController: null,
      setRows: [],
      detailCache: new Map(),
      judgments: loadJudgments()
    };

    const API_BASE = (() => {
      const host = window.location.hostname;
      const port = window.location.port;
      if ((host === "127.0.0.1" || host === "localhost") && port) {
        return "";
      }
      return "http://127.0.0.1:8766";
    })();

    const SEMANTIC_BUCKET_FETCH_MIN = 60;
    const SEMANTIC_BUCKET_MIN_RELEVANCE = 0.25;
    const RELATED_BUCKET_MIN_STRENGTH = 0.58;
    const RELATED_BUCKET_MIN_CONFIDENCE = 0.50;
    const BRAND_STATUS = "UMLS 2.0";
    const CONTRAINDICATION_RELATION_MARKERS = [
      "contraindicat"
    ];
    const GENE_BUCKET_DRUG_LIKE_RELAS = new Set([
      "chemotherapy_regimen_has_component",
      "contraindicated_class_of",
      "has_gdc_value",
      "may_be_treated_by"
    ]);
    const GENE_PROTEIN_SEMANTIC_TYPES = new Set([
      "amino acid sequence",
      "amino acid, peptide, or protein",
      "gene or genome",
      "nucleic acid, nucleoside, or nucleotide",
      "nucleotide sequence"
    ]);
    const GENE_PROTEIN_ALWAYS_SEMANTIC_TYPES = new Set([
      "amino acid sequence",
      "gene or genome",
      "nucleotide sequence"
    ]);
    const GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES = new Set([
      "amino acid, peptide, or protein",
      "nucleic acid, nucleoside, or nucleotide"
    ]);
    const GENE_PROTEIN_LABEL_MARKERS = new Set([
      "allele",
      "antibody",
      "antigen",
      "codon",
      "codons",
      "cytokine",
      "enzyme",
      "exon",
      "exons",
      "factor",
      "factors",
      "gene",
      "genes",
      "globin",
      "hemoglobin",
      "immunoglobulin",
      "intron",
      "introns",
      "interleukin",
      "kinase",
      "protein",
      "proteins",
      "promoter",
      "promoters",
      "receptor",
      "receptors"
    ]);
    const OBSERVATION_LAB_SEMANTIC_TYPES = new Set([
      "laboratory procedure"
    ]);
    const MEASUREMENT_OBSERVATION_SEMANTIC_TYPES = new Set([
      "diagnostic procedure",
      "laboratory procedure"
    ]);
    const MEASUREMENT_OBSERVATION_LABEL_MARKERS = new Set([
      "assay",
      "assays",
      "level",
      "levels",
      "measurement",
      "measurements",
      "panel",
      "panels",
      "ratio",
      "ratios",
      "test",
      "tests"
    ]);
    const DOSAGE_FORM_SEMANTIC_TYPES = new Set([
      "biomedical or dental material"
    ]);
    const DOSAGE_FORM_LABEL_MARKERS = [
      "dosage form"
    ];
    const CLINICAL_DRUG_FORMULATION_SEMANTIC_TYPES = new Set([
      "clinical drug"
    ]);
    const CLINICAL_DRUG_FORMULATION_UNITS = new Set([
      "mg",
      "mcg",
      "meq",
      "ml",
      "unt",
      "unit",
      "units"
    ]);
    const CLINICAL_DRUG_FORMULATION_TERMS = new Set([
      "capsule",
      "injection",
      "solution",
      "tablet",
      "tablets"
    ]);
    const BROAD_CHEMICAL_FRAGMENT_CLASSES = new Set([
      "chlorides",
      "nitrates",
      "oxides",
      "phosphates",
      "salts",
      "sulfates"
    ]);
    const BROAD_CHEMICAL_FRAGMENT_MODIFIERS = new Set([
      "inorganic",
      "organic"
    ]);
    const NOISY_BROAD_RELATION_SOURCES = new Set(["ccpss"]);
    const NOISY_BROAD_RELATION_RELAS = new Set([
      "clinically_associated_with",
      "clinically associated with",
      "inverse clinically associated with",
      "inverse_clinically_associated_with"
    ]);
    const NOISY_BROAD_RELATION_BUCKET_KEYS = new Set(["CHEM", "CLIN_ATTR", "GENE", "PROC"]);
    const RELATION_OVERLAP_STOPWORDS = new Set([
      "and",
      "for",
      "has",
      "nos",
      "of",
      "the",
      "to",
      "with",
      "procedure",
      "procedures",
      "screen",
      "screening",
      "therapy",
      "treatment"
    ]);
    const DEFAULT_SEMANTIC_RESULT_BUCKETS = [
      {
        key: "DISO_DISEASE",
        label: "Diseases & Syndromes",
        code: "DISO",
        semanticTypes: [
          "acquired abnormality",
          "anatomical abnormality",
          "cell or molecular dysfunction",
          "congenital abnormality",
          "disease or syndrome",
          "experimental model of disease",
          "injury or poisoning",
          "mental or behavioral dysfunction",
          "neoplastic process",
          "pathologic function"
        ]
      },
      {
        key: "DISO_FINDING",
        label: "Findings & Symptoms",
        code: "FIND",
        semanticTypes: [
          "finding",
          "sign or symptom"
        ]
      },
      { key: "CHEM", label: "Drugs", code: "CHEM", codes: ["CHEM"] },
      { key: "PROC", label: "Procedures", code: "PROC", codes: ["PROC"] },
      {
        key: "CLIN_ATTR",
        label: "Observations & Lab Results",
        code: "OBS",
        codes: ["OBS"],
        semanticTypes: [
          "clinical attribute",
          "laboratory procedure",
          "laboratory or test result"
        ]
      },
      {
        key: "GENE",
        label: "Genes, Amino Acids, Peptides, Proteins",
        code: "GENE",
        codes: ["GENE"],
        semanticTypes: [
          "amino acid sequence",
          "amino acid, peptide, or protein",
          "gene or genome",
          "nucleic acid, nucleoside, or nucleotide",
          "nucleotide sequence"
        ]
      },
      { key: "DEVI", label: "Devices", code: "DEVI", codes: ["DEVI"] },
      {
        key: "ORGANISM",
        label: "Organisms",
        code: "LIVB",
        semanticTypes: [
          "alga",
          "archaeon",
          "bacterium",
          "fungus",
          "rickettsia or chlamydia",
          "virus"
        ]
      },
      {
        key: "PEOPLE",
        label: "People & Populations",
        code: "LIVB",
        semanticTypes: [
          "age group",
          "family group",
          "group",
          "human",
          "patient or disabled group",
          "population group",
          "professional or occupational group"
        ]
      },
      { key: "ANAT", label: "Anatomy", code: "ANAT", codes: ["ANAT"] }
    ];
    const DEFAULT_PARAGRAPH_TESTS = [
      "Patient with heart failure with reduced ejection fraction reported worsening orthopnea and leg edema after missing several doses of furosemide. Exam showed bibasilar crackles, and echocardiogram demonstrated reduced ejection fraction.",
      "Computed tomography angiography showed acute pulmonary embolism with right heart strain. The patient was started on apixaban after venous duplex ultrasound confirmed acute deep vein thrombosis.",
      "A patient with poorly controlled type 2 diabetes mellitus presented with foot ulcer drainage and exposed bone. Foot MRI was concerning for diabetic foot osteomyelitis, and bone biopsy was planned before narrowing antibiotics.",
      "Electroencephalogram captured epileptiform discharges during evaluation for generalized tonic clonic seizure. Levetiracetam was started, and seizure precautions were continued because of persistent postictal confusion.",
      "The patient had heat intolerance, fine tremor, and a suppressed TSH with elevated free thyroxine. Endocrinology recommended methimazole and thyroid uptake scan for suspected thyrotoxicosis.",
      "A patient with plaque psoriasis had erythematous plaques on extensor surfaces with silvery scale. Joint pain raised concern for psoriatic arthritis, although no joint erosion was seen on the initial radiograph.",
      "Coronary angiography demonstrated critical coronary stenosis after non ST elevation myocardial infarction. Heparin infusion was continued until percutaneous coronary intervention, and the team monitored for recurrent ischemia.",
      "The patient denied pleuritic chest pain, but computed tomography angiography later showed segmental pulmonary embolus. There was no evidence of right heart strain on echocardiogram.",
      "Researchers used hemoglobin A1c and medication exposure to identify poorly controlled type 2 diabetes mellitus in electronic health records. Elevated albumin creatinine ratio was associated with progressive renal disease during follow up.",
      "A procedure note documented ultrasound guided venous access for central venous catheter placement. The right internal jugular central line was placed using sterile technique, and the team monitored for line associated infection.",
      "Brain MRI showed acute infarct in the right MCA territory after sudden left sided weakness and facial droop. Aspirin and statin were started, but persistent neurologic deficit remained at discharge.",
      "The cohort study compared patients receiving vancomycin for diabetic foot osteomyelitis with patients treated for soft tissue infection alone. Exposed bone and positive bone biopsy were associated with higher amputation risk.",
      "Emergency department evaluation showed fever, dysuria, and flank pain. Urinalysis had nitrites and pyuria, urine culture grew Escherichia coli, and ceftriaxone was given for acute pyelonephritis.",
      "Postoperative patient developed hypoxia with bibasilar infiltrates on chest radiograph. Sputum culture and elevated procalcitonin supported bacterial pneumonia, and oxygen therapy plus ceftriaxone were started.",
      "The oncology note described invasive ductal breast carcinoma with estrogen receptor positive disease. She received lumpectomy followed by adjuvant radiation therapy and tamoxifen.",
      "Rheumatology evaluated morning stiffness and symmetric MCP swelling. Positive rheumatoid factor and anti cyclic citrullinated peptide antibodies supported rheumatoid arthritis, and methotrexate was started.",
      "He presented with hematemesis and melena after heavy NSAID use. Endoscopy found a bleeding gastric ulcer, and pantoprazole infusion was started before transfusion.",
      "After total knee arthroplasty, calf swelling and elevated D-dimer prompted venous duplex ultrasound. Acute deep vein thrombosis was treated with apixaban, and pulmonary embolism symptoms were reviewed.",
      "An ICU patient with septic shock required norepinephrine, broad spectrum antibiotics, and lactate monitoring. Blood cultures later grew methicillin resistant Staphylococcus aureus.",
      "A child with wheezing and increased work of breathing had asthma exacerbation triggered by rhinovirus. Albuterol nebulizers, systemic corticosteroids, and pulse oximetry monitoring were ordered.",
      "After intravenous contrast exposure, creatinine increased from baseline and urine output declined. Nephrology diagnosed acute kidney injury, reviewed urinalysis with granular casts, and recommended isotonic fluids while holding lisinopril.",
      "Electrocardiogram showed ST elevation in the inferior leads with elevated troponin. Emergent coronary angiography found right coronary artery occlusion, and percutaneous coronary intervention with stent placement was performed.",
      "A pregnant patient at 34 weeks developed severe hypertension, headache, and proteinuria. Obstetrics diagnosed preeclampsia with severe features and started magnesium sulfate before induction of labor.",
      "The patient had microcytic anemia with low ferritin and positive fecal occult blood testing. Colonoscopy found a bleeding colon mass, and packed red blood cell transfusion was ordered.",
      "A patient with chronic hepatitis C had elevated transaminases and thrombocytopenia. Liver ultrasound showed cirrhosis with ascites, and hepatology started spironolactone for volume management.",
      "Blood glucose was 38 mg/dL after excess insulin use, and the patient was diaphoretic and confused. Dextrose was given for severe hypoglycemia, and continuous glucose monitoring was reviewed.",
      "A patient with fever, neck stiffness, and photophobia underwent lumbar puncture. Cerebrospinal fluid showed neutrophilic pleocytosis and low glucose, so ceftriaxone and vancomycin were started for bacterial meningitis.",
      "The oncology trial enrolled patients with EGFR mutated non small cell lung cancer. Osimertinib improved progression free survival compared with platinum chemotherapy in participants with brain metastases.",
      "A patient with obstructive sleep apnea reported daytime somnolence and loud snoring. Polysomnography showed an elevated apnea hypopnea index, and continuous positive airway pressure was prescribed.",
      "The patient developed urinary retention after spinal anesthesia. Bladder scan showed 800 mL post void residual, and a Foley catheter was inserted before starting tamsulosin.",
      "A child with fever and barking cough had inspiratory stridor on exam. Neck radiograph suggested croup, and dexamethasone plus nebulized epinephrine were administered.",
      "The transplant recipient developed rising creatinine and decreased tacrolimus trough levels after missed doses. Kidney biopsy showed acute cellular rejection, and high dose methylprednisolone was started."
    ];
    let clinicalNoteSuggestions = [];
    let paragraphTests = [];
    let semanticResultBucketDefs = DEFAULT_SEMANTIC_RESULT_BUCKETS;
    let semanticResultBucketsReady = Promise.resolve();
    let semanticExpansionProfiles = [];
    let semanticExpansionProfilesReady = Promise.resolve();

    async function loadClinicalNoteSuggestions() {
      try {
        const response = await fetch(`${API_BASE}/search_quality_suggestions.json`);
        if (!response.ok) throw new Error(`suggestions ${response.status}`);
        const payload = await response.json();
        clinicalNoteSuggestions = Array.isArray(payload)
          ? payload.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
      } catch (err) {
        clinicalNoteSuggestions = [];
      }
    }

    async function loadParagraphTests() {
      try {
        const response = await fetch(`${API_BASE}/search_quality_paragraphs.json`);
        if (!response.ok) throw new Error(`paragraphs ${response.status}`);
        const payload = await response.json();
        paragraphTests = Array.isArray(payload)
          ? payload.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
      } catch (err) {
        paragraphTests = DEFAULT_PARAGRAPH_TESTS;
      }
      if (!paragraphTests.length) paragraphTests = DEFAULT_PARAGRAPH_TESTS;
    }

    async function loadSemanticResultBuckets() {
      try {
        const response = await fetch(`${API_BASE}/search_quality_semantic_buckets.json`);
        if (!response.ok) throw new Error(`semantic buckets ${response.status}`);
        const payload = await response.json();
        const buckets = normalizeSemanticResultBuckets(payload);
        semanticResultBucketDefs = buckets.length ? buckets : DEFAULT_SEMANTIC_RESULT_BUCKETS;
      } catch (err) {
        semanticResultBucketDefs = DEFAULT_SEMANTIC_RESULT_BUCKETS;
      }
    }

    function normalizeSemanticResultBuckets(payload) {
      if (!Array.isArray(payload)) return [];
      const seen = new Set();
      return payload.map((bucket) => {
        const key = String(bucket?.key || "").trim();
        const label = String(bucket?.label || "").trim();
        const code = String(bucket?.code || "").trim();
        const semanticTypes = Array.isArray(bucket?.semanticTypes)
          ? bucket.semanticTypes.map((value) => String(value || "").trim().toLowerCase()).filter(Boolean)
          : [];
        const codes = Array.isArray(bucket?.codes)
          ? bucket.codes.map((value) => String(value || "").trim()).filter(Boolean)
          : [];
        if (!key || !label || seen.has(key)) return null;
        seen.add(key);
        return { key, label, code, semanticTypes, codes };
      }).filter(Boolean);
    }

    function renderSemanticGroupFilter() {
      if (!els.semanticGroupFilter) return;
      const selected = new Set(selectedSemanticBucketKeys());
      els.semanticGroupFilter.innerHTML = semanticResultBucketDefs.map((bucket) => `
        <option value="${esc(bucket.key)}"${selected.has(bucket.key) ? " selected" : ""}>${esc(bucket.label)}</option>
      `).join("");
    }

    function selectedSemanticBucketKeys() {
      if (!els.semanticGroupFilter) return [];
      return Array.from(els.semanticGroupFilter.selectedOptions || [])
        .map((option) => String(option.value || "").trim())
        .filter(Boolean);
    }

    function semanticBucketFilterQueryParam(keys = selectedSemanticBucketKeys()) {
      return keys.length ? `&semantic_buckets=${encodeURIComponent(keys.join(","))}` : "";
    }

    function activeSemanticResultBucketDefs() {
      const selected = new Set(state.selectedSemanticBucketKeys || []);
      if (!selected.size) return semanticResultBucketDefs;
      return semanticResultBucketDefs.filter((bucket) => selected.has(bucket.key));
    }

    async function loadSemanticExpansionProfiles() {
      try {
        const response = await fetch(`${API_BASE}/search_quality_expansion_profiles.json`);
        if (!response.ok) throw new Error(`expansion profiles ${response.status}`);
        const payload = await response.json();
        semanticExpansionProfiles = normalizeSemanticExpansionProfiles(payload);
      } catch (err) {
        semanticExpansionProfiles = [];
      }
    }

    function normalizeSemanticExpansionProfiles(payload) {
      if (!Array.isArray(payload)) return [];
      return payload.map((profile) => {
        const triggerPatterns = Array.isArray(profile?.trigger_patterns)
          ? profile.trigger_patterns.map((pattern) => compileExpansionPattern(pattern)).filter(Boolean)
          : [];
        const items = Array.isArray(profile?.items)
          ? profile.items
              .map((item) => ({
                cui: String(item?.cui || "").trim(),
                label: String(item?.label || item?.name || "").trim(),
                semantic_type: String(item?.semantic_type || "").trim(),
                semantic_group: String(item?.semantic_group || profile?.target_group || "").trim(),
                semantic_group_label: String(item?.semantic_group_label || "").trim()
              }))
              .filter((item) => item.cui && item.label)
          : [];
        return {
          id: String(profile?.id || "").trim(),
          label: String(profile?.label || profile?.id || "semantic expansion").trim(),
          target_bucket: String(profile?.target_bucket || "").trim(),
          target_group: String(profile?.target_group || "").trim(),
          source: String(profile?.source || profile?.label || profile?.id || "semantic expansion").trim(),
          source_rank: Number(profile?.source_rank || 0),
          triggerPatterns,
          items
        };
      }).filter((profile) => (profile.target_bucket || profile.target_group) && profile.triggerPatterns.length && profile.items.length);
    }

    function compileExpansionPattern(pattern) {
      try {
        return new RegExp(String(pattern || ""), "i");
      } catch (err) {
        return null;
      }
    }

    const els = {};
    for (const id of [
      "status", "query", "topK", "semanticGroupFilter", "searchBtn", "querySet", "runSetBtn",
      "includeRelated", "saveJudgmentsBtn", "clearJudgmentsBtn", "exportBtn", "metrics", "results", "setResults",
      "searchProgress", "searchFeedback", "querySetFeedback",
      "clinicalSuggestionSelect", "paragraphTestSelect"
    ]) {
      els[id] = document.getElementById(id);
    }

    function setBrandStatus() {
      if (els.status) els.status.textContent = BRAND_STATUS;
    }

    function setSearchInFlight(active) {
      if (els.searchProgress) els.searchProgress.hidden = !active;
      if (els.results) els.results.setAttribute("aria-busy", active ? "true" : "false");
    }

    function setSearchFeedback(message = "", kind = "") {
      if (!els.searchFeedback) return;
      const text = String(message || "").trim();
      els.searchFeedback.textContent = text;
      els.searchFeedback.hidden = !text;
      els.searchFeedback.classList.toggle("is-error", kind === "error");
    }

    function setQuerySetFeedback(message = "", kind = "") {
      if (!els.querySetFeedback) return;
      const text = String(message || "").trim();
      els.querySetFeedback.textContent = text;
      els.querySetFeedback.hidden = !text;
      els.querySetFeedback.classList.toggle("is-error", kind === "error");
    }

    function esc(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function fmtNum(value) {
      return Math.round(Number(value) || 0).toLocaleString();
    }

    function fmtPct(value) {
      if (!Number.isFinite(value)) return "0%";
      return `${(value * 100).toFixed(1)}%`;
    }

    function escapeRegex(value) {
      return String(value ?? "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function renderClinicalNoteSuggestions() {
      if (!els.clinicalSuggestionSelect) return;
      els.clinicalSuggestionSelect.innerHTML = [
        '<option value="">Select a clinical note...</option>',
        ...clinicalNoteSuggestions.map((query, index) => `
          <option value="${esc(index)}">${esc(query)}</option>`)
      ].join("");
    }

    function renderParagraphTests() {
      if (!els.paragraphTestSelect) return;
      els.paragraphTestSelect.innerHTML = [
        '<option value="">Select a paragraph test...</option>',
        ...paragraphTests.map((query, index) => `
          <option value="${esc(index)}">${fmtNum(index + 1)}. ${esc(query)}</option>`)
      ].join("");
    }

    function runSelectedDropdownQuery(select, items) {
      if (!select) return;
      if (select.value === "") return;
      const index = Number(select.value);
      if (!Number.isInteger(index) || index < 0 || index >= items.length) return;
      els.query.value = items[index];
      select.value = "";
      runSearch();
    }

    function loadJudgments() {
      try {
        return JSON.parse(localStorage.getItem("qe_search_server_judgments") || "{}");
      } catch (err) {
        return {};
      }
    }

    function saveJudgments() {
      localStorage.setItem("qe_search_server_judgments", JSON.stringify(state.judgments));
    }

    function judgmentKey(query, docId) {
      return `${query}\t${docId}`;
    }

    async function api(path, options = {}) {
      const url = `${API_BASE}${path}`;
      let response;
      try {
        response = await fetch(url, {
          method: options.method || "GET",
          headers: {
            "Accept": "application/json",
            ...(options.body ? { "Content-Type": "application/json" } : {})
          },
          signal: options.signal,
          body: options.body ? JSON.stringify(options.body) : undefined
        });
      } catch (err) {
        if (err?.name === "AbortError") throw err;
        throw new Error(`Cannot reach search_quality_server.py at ${API_BASE || "this origin"}. Start it with: python3 scripts/search_quality_server.py --port 8766`);
      }

      const contentType = response.headers.get("content-type") || "";
      const text = await response.text();
      if (!contentType.includes("application/json")) {
        throw new Error(`Expected JSON from ${url}, but got ${contentType || "unknown content"}. Open http://127.0.0.1:8766/ or start the server with: python3 scripts/search_quality_server.py --port 8766`);
      }

      let payload;
      try {
        payload = JSON.parse(text);
      } catch (err) {
        throw new Error(`Invalid JSON from ${url}: ${text.slice(0, 120)}`);
      }
      if (!response.ok) throw new Error(payload.error || response.statusText);
      return payload;
    }

    async function loadStatus() {
      try {
        state.status = await api("/api/status");
      } catch (err) {
        state.status = null;
      }
      setBrandStatus();
      renderMetrics();
    }

    async function loadServerJudgments() {
      try {
        const payload = await api("/api/judgments");
        for (const row of payload.judgments || []) {
          state.judgments[judgmentKey(row.query, row.doc_id)] = row;
        }
        saveJudgments();
        renderMetrics();
      } catch (err) {
        setBrandStatus();
      }
    }

    async function persistJudgmentsToServer() {
      const payload = await api("/api/judgments", {
        method: "POST",
        body: { judgments: Object.values(state.judgments) }
      });
      setBrandStatus();
      renderMetrics();
    }

    async function runSearch() {
      const query = els.query.value.trim();
      const topK = Math.max(18, Math.min(100, Number(els.topK.value) || SEMANTIC_BUCKET_FETCH_MIN));
      const includeRelated = els.includeRelated && els.includeRelated.checked ? "1" : "0";
      const semanticBucketKeys = selectedSemanticBucketKeys();
      const searchK = includeRelated === "1" ? topK : Math.max(topK, SEMANTIC_BUCKET_FETCH_MIN);
      if (!query) {
        setSearchFeedback("Enter text, a CUI, or a source code before searching.", "error");
        return;
      }
      state.searchAbortController?.abort();
      const searchId = state.searchRequestSeq + 1;
      state.searchRequestSeq = searchId;
      const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      state.searchAbortController = controller;
      els.searchBtn.disabled = true;
      setSearchInFlight(true);
      setSearchFeedback();
      setBrandStatus();
      try {
        const payload = await api(
          `/api/search?q=${encodeURIComponent(query)}&k=${searchK}&related=${includeRelated}${semanticBucketFilterQueryParam(semanticBucketKeys)}`,
          { signal: controller?.signal }
        );
        if (searchId !== state.searchRequestSeq) return;
        await Promise.all([semanticResultBucketsReady, semanticExpansionProfilesReady]);
        if (searchId !== state.searchRequestSeq) return;
        state.lastQuery = query;
        state.lastResults = payload.hits || [];
        state.lastSemanticViews = payload.semantic_views || [];
        state.lastSemanticViewSources = payload.semantic_view_sources || [];
        state.lastSemanticGroupViews = payload.semantic_group_views || [];
        state.lastSemanticResultBuckets = payload.semantic_result_buckets || [];
        state.lastRelatedResultBuckets = payload.related_result_buckets || [];
        state.lastScoring = payload.scoring || null;
        state.includeRelated = includeRelated === "1";
        state.selectedSemanticBucketKeys = semanticBucketKeys;
        setBrandStatus();
        setSearchFeedback();
        renderResults();
        renderMetrics();
      } catch (err) {
        if (err?.name === "AbortError") return;
        if (searchId !== state.searchRequestSeq) return;
        setSearchFeedback(err?.message || "Search failed.", "error");
        setBrandStatus();
      } finally {
        if (searchId === state.searchRequestSeq) {
          state.searchAbortController = null;
          setSearchInFlight(false);
          els.searchBtn.disabled = false;
        }
      }
    }

    function setJudgment(hit, grade) {
      const key = judgmentKey(state.lastQuery, hit.doc_id);
      if (grade) {
        state.judgments[key] = {
          query: state.lastQuery,
          doc_id: hit.doc_id,
          cui: hit.cui,
          view: hit.view,
          score: hit.score,
          grade,
          labels: hit.labels || []
        };
      } else {
        delete state.judgments[key];
      }
      saveJudgments();
      renderResults();
      renderMetrics();
      persistJudgmentsToServer().catch((err) => {
        setBrandStatus();
      });
    }

    function semanticGroupForHit(hit) {
      const code = String(hit.semantic_group || "").trim() || "OTHER";
      const label = String(hit.semantic_group_label || "").trim() || "Other";
      return { code, label };
    }

    function semanticTypeNamesForHit(hit) {
      return new Set((hit.semantic_types || [])
        .map((item) => String(item?.name || item?.sty || item?.semantic_type || "").trim().toLowerCase())
        .filter(Boolean));
    }

    function isClinicalAttributeHit(hit) {
      return semanticTypeNamesForHit(hit).has("clinical attribute");
    }

    function hasAnyType(typeNames, expectedTypes) {
      return (expectedTypes || []).some((typeName) => typeNames.has(typeName));
    }

    function semanticTypesForBucketKey(bucketKey) {
      const bucket = semanticResultBucketDefs.find((item) => item.key === bucketKey);
      return bucket?.semanticTypes || [];
    }

    function hitMatchesSemanticBucket(hit, bucket) {
      if (bucket.key === "CHEM" && hitIsGeneProteinBucketItem(hit)) return false;
      if (bucket.key === "CHEM" && hitIsDosageFormBucketNoise(hit)) return false;
      if (bucket.key === "CHEM" && hitIsBroadChemicalFragmentBucketNoise(hit)) return false;
      if (bucket.key === "CLIN_ATTR" && hitIsMeasurementObservationBucketItem(hit)) return true;
      if (bucket.key === "GENE" && hitHasAmbiguousGeneProteinType(hit) && !hitIsGeneProteinBucketItem(hit)) {
        return false;
      }
      if (bucket.key === "PROC" && hitIsObservationLabBucketItem(hit)) return false;
      if (bucket.key === "PROC" && hitIsMeasurementObservationBucketItem(hit)) return false;
      const typeNames = semanticTypeNamesForHit(hit);
      const typeMatch = hasAnyType(typeNames, bucket.semanticTypes || []);
      const groupInfo = semanticGroupForHit(hit);
      const codeMatch = new Set(bucket.codes || []).has(groupInfo.code);
      return typeMatch || codeMatch;
    }

    function relationMatchesSemanticBucket(relation, bucket, groupCode) {
      if (bucket.key === "CHEM" && relationIsGeneProteinBucketItem(relation)) return false;
      if (bucket.key === "CHEM" && relationIsDosageFormBucketNoise(relation)) return false;
      if (bucket.key === "CHEM" && relationIsClinicalDrugFormulationNoise(relation)) return false;
      if (bucket.key === "CHEM" && relationIsBroadChemicalFragmentBucketNoise(relation)) return false;
      if (bucket.key === "CLIN_ATTR" && relationIsMeasurementObservationBucketItem(relation)) return true;
      if (
        bucket.key === "GENE" &&
        relationHasAmbiguousGeneProteinType(relation) &&
        !relationIsGeneProteinBucketItem(relation)
      ) {
        return false;
      }
      if (bucket.key === "PROC" && relationIsObservationLabBucketItem(relation)) return false;
      if (bucket.key === "PROC" && relationIsMeasurementObservationBucketItem(relation)) return false;
      const semanticTypes = bucket.semanticTypes || [];
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      const typeMatch = semanticTypes.includes(relationType);
      const codeMatch = new Set(bucket.codes || []).has(groupCode);
      return typeMatch || codeMatch;
    }

    function relationVisibleInSemanticBucket(relation, bucket, groupCode) {
      if (!relationMatchesSemanticBucket(relation, bucket, groupCode)) return false;
      if (isContraindicationRelation(relation)) return false;
      if (bucket.key === "GENE" && isDrugLikeGeneBucketRelation(relation)) return false;
      if (isNoisyBroadRelation(relation, bucket)) return false;
      return true;
    }

    function relationTextValue(relation) {
      return [
        relation.rela,
        relation.relation,
        relation.relation_group,
        relation.category,
        relation.category_label,
        relation.source,
        relation.label
      ].map((value) => String(value || "").toLowerCase()).join(" ");
    }

    function isContraindicationRelation(relation) {
      const value = relationTextValue(relation);
      return CONTRAINDICATION_RELATION_MARKERS.some((marker) => value.includes(marker));
    }

    function isDrugLikeGeneBucketRelation(relation) {
      const rela = String(relation.rela || relation.relation || "").trim().toLowerCase();
      const relationGroup = String(relation.relation_group || "").trim().toLowerCase();
      if (GENE_BUCKET_DRUG_LIKE_RELAS.has(rela)) return true;
      if (relationGroup === "treatment" && rela !== "has_target") return true;
      return false;
    }

    function hitIsGeneProteinBucketItem(hit) {
      const typeNames = semanticTypeNamesForHit(hit);
      if ([...typeNames].some((typeName) => GENE_PROTEIN_ALWAYS_SEMANTIC_TYPES.has(typeName))) {
        return true;
      }
      if (!hitHasAmbiguousGeneProteinType(hit)) return false;
      const labels = Array.isArray(hit.labels) ? hit.labels.join(" ") : "";
      return hasGeneProteinLabelMarker(`${hit.name || hit.label || ""} ${labels}`);
    }

    function hitHasAmbiguousGeneProteinType(hit) {
      const typeNames = semanticTypeNamesForHit(hit);
      return [...typeNames].some((typeName) => GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES.has(typeName));
    }

    function hasGeneProteinLabelMarker(value) {
      const text = String(value || "").toLowerCase();
      const tokens = text.match(/[a-z0-9]+/g) || [];
      if (tokens.some((token) => GENE_PROTEIN_LABEL_MARKERS.has(token))) return true;
      return text.includes("growth factor") || text.includes("tumor necrosis factor");
    }

    function hitIsObservationLabBucketItem(hit) {
      const typeNames = semanticTypeNamesForHit(hit);
      return [...typeNames].some((typeName) => OBSERVATION_LAB_SEMANTIC_TYPES.has(typeName));
    }

    function hasMeasurementObservationLabelMarker(value) {
      const tokens = String(value || "").toLowerCase().match(/[a-z0-9]+/g) || [];
      return tokens.some((token) => MEASUREMENT_OBSERVATION_LABEL_MARKERS.has(token));
    }

    function hitIsMeasurementObservationBucketItem(hit) {
      const typeNames = semanticTypeNamesForHit(hit);
      if (![...typeNames].some((typeName) => MEASUREMENT_OBSERVATION_SEMANTIC_TYPES.has(typeName))) {
        return false;
      }
      const labels = Array.isArray(hit.labels) ? hit.labels.join(" ") : "";
      return hasMeasurementObservationLabelMarker(`${hit.name || hit.label || ""} ${labels}`);
    }

    function relationIsGeneProteinBucketItem(relation) {
      const category = String(relation.category || "").trim().toLowerCase();
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      if (category === "gene_protein" || GENE_PROTEIN_ALWAYS_SEMANTIC_TYPES.has(relationType)) {
        return true;
      }
      if (!GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES.has(relationType)) return false;
      return hasGeneProteinLabelMarker(relation.label || relation.target_label);
    }

    function relationHasAmbiguousGeneProteinType(relation) {
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      return GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES.has(relationType);
    }

    function relationIsObservationLabBucketItem(relation) {
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      return OBSERVATION_LAB_SEMANTIC_TYPES.has(relationType);
    }

    function relationIsMeasurementObservationBucketItem(relation) {
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      if (!MEASUREMENT_OBSERVATION_SEMANTIC_TYPES.has(relationType)) return false;
      return hasMeasurementObservationLabelMarker(relation.label || relation.target_label || "");
    }

    function hitIsDosageFormBucketNoise(hit) {
      const typeNames = semanticTypeNamesForHit(hit);
      const labels = Array.isArray(hit.labels) ? hit.labels.join(" ") : "";
      const label = `${hit.name || hit.label || ""} ${labels}`.toLowerCase();
      return [...typeNames].some((typeName) => DOSAGE_FORM_SEMANTIC_TYPES.has(typeName)) &&
        DOSAGE_FORM_LABEL_MARKERS.some((marker) => label.includes(marker));
    }

    function relationIsDosageFormBucketNoise(relation) {
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      const label = String(relation.label || relation.target_label || "").toLowerCase();
      return DOSAGE_FORM_SEMANTIC_TYPES.has(relationType) &&
        DOSAGE_FORM_LABEL_MARKERS.some((marker) => label.includes(marker));
    }

    function relationIsClinicalDrugFormulationNoise(relation) {
      const relationType = String(relation.semantic_type || "").trim().toLowerCase();
      if (!CLINICAL_DRUG_FORMULATION_SEMANTIC_TYPES.has(relationType)) return false;
      const label = String(relation.label || relation.target_label || "").toLowerCase();
      const tokens = label.match(/[a-z]+/g) || [];
      const hasStrength = /\b\d+(?:\.\d+)?\b/.test(label) &&
        tokens.some((token) => CLINICAL_DRUG_FORMULATION_UNITS.has(token));
      const hasForm = tokens.some((token) => CLINICAL_DRUG_FORMULATION_TERMS.has(token));
      return hasStrength || hasForm;
    }

    function isBroadChemicalFragmentLabel(value) {
      const text = String(value || "").trim().toLowerCase();
      if (!text.includes(",")) return false;
      const [left, right] = text.split(",", 2).map((part) => part.trim());
      const leftTokens = left.match(/[a-z]+/g) || [];
      const rightTokens = right.match(/[a-z]+/g) || [];
      return leftTokens.some((token) => BROAD_CHEMICAL_FRAGMENT_CLASSES.has(token)) &&
        rightTokens.some((token) => BROAD_CHEMICAL_FRAGMENT_MODIFIERS.has(token));
    }

    function hitIsBroadChemicalFragmentBucketNoise(hit) {
      return isBroadChemicalFragmentLabel(hit.name || hit.label || "");
    }

    function relationIsBroadChemicalFragmentBucketNoise(relation) {
      return isBroadChemicalFragmentLabel(relation.label || relation.target_label || "");
    }

    function relationOverlapTokens(value) {
      const tokens = String(value || "").toLowerCase().match(/[a-z0-9]+/g) || [];
      return new Set(tokens.filter((token) =>
        token.length > 2 && !RELATION_OVERLAP_STOPWORDS.has(token)
      ));
    }

    function relationHasSourceLabelOverlap(relation) {
      const sourceTokens = relationOverlapTokens(relation.source_name || relation.source_label);
      const labelTokens = relationOverlapTokens(relation.label || relation.target_label);
      return [...sourceTokens].some((token) => labelTokens.has(token));
    }

    function isNoisyBroadRelation(relation, bucket) {
      if (!NOISY_BROAD_RELATION_BUCKET_KEYS.has(bucket.key)) return false;
      const source = String(relation.source || "").trim().toLowerCase();
      if (!NOISY_BROAD_RELATION_SOURCES.has(source)) return false;
      const relationValues = [
        String(relation.rela || "").trim().toLowerCase(),
        String(relation.relation || "").trim().toLowerCase()
      ];
      if (!relationValues.some((value) => NOISY_BROAD_RELATION_RELAS.has(value))) return false;
      return !relationHasSourceLabelOverlap(relation);
    }

    function relationIsRepresentedInResultBuckets(relation, groupCode) {
      return semanticResultBucketDefs.some((bucket) =>
        relationVisibleInSemanticBucket(relation, bucket, groupCode)
      );
    }

    function unrepresentedSemanticGroupViews(groupViews) {
      return (groupViews || []).map((view) => {
        const groupCode = String(view.semantic_group || "").trim();
        const items = (view.items || []).filter((relation) =>
          !relationIsRepresentedInResultBuckets(relation, groupCode)
        );
        return { ...view, items };
      }).filter((view) => view.items.length);
    }

    function semanticClassLabelForTypeNames(typeNames) {
      if (hasAnyType(typeNames, semanticTypesForBucketKey("DISO_DISEASE"))) return "Disease or Syndrome";
      if (typeNames.has("sign or symptom")) return "Sign or Symptom";
      if (typeNames.has("finding")) return "Finding";
      if (typeNames.has("clinical attribute")) return "Clinical Observation";
      return "";
    }

    function semanticDisplayTypeForHit(hit) {
      const typeNames = semanticTypeNamesForHit(hit);
      return semanticClassLabelForTypeNames(typeNames)
        || (hit.semantic_types || [])[0]?.name
        || hit.semantic_group_label
        || "";
    }

    function isReadableClinicalAttributeLabel(label) {
      const value = String(label || "").trim();
      if (!value) return false;
      if (value.includes(":") || value.includes("^")) return false;
      if (/^[A-Z0-9._-]+$/.test(value)) return false;
      return /[A-Za-z]/.test(value);
    }

    function clinicalAttributeDisplayName(hit, labels) {
      const readable = (labels || []).find((label) => isReadableClinicalAttributeLabel(label));
      if (readable) return readable;
      const name = String(hit.name || labels?.[0] || hit.cui || "").trim();
      const prefix = name.split(":")[0].trim();
      return prefix || name || hit.cui;
    }

    function displayNameForHit(hit) {
      const labels = hit.labels || [];
      if (isClinicalAttributeHit(hit)) return clinicalAttributeDisplayName(hit, labels);
      return hit.name || labels[0] || hit.cui;
    }

    function imageSourceLabel(image) {
      const parts = [];
      if (image.source) parts.push(image.source.replaceAll("_", " "));
      if (image.license) parts.push(image.license);
      return parts.join(" · ");
    }

    function renderImageGallery(images, compact = false) {
      const visible = (images || []).filter((image) => image.thumbnail_url || image.image_url).slice(0, compact ? 2 : 4);
      if (!visible.length) return "";
      return `
        <div class="detail-section concept-images-section">
          <div class="detail-title">Open-License Images</div>
          <div class="${compact ? "concept-image-strip compact" : "concept-image-strip"}">
            ${visible.map((image) => {
              const href = image.source_url || image.file_page_url || image.image_url || "#";
              const src = image.thumbnail_url || image.image_url || "";
              return `
                <a class="concept-image-card" href="${esc(href)}" target="_blank" rel="noreferrer" title="${esc(image.title || "")}">
                  <img src="${esc(src)}" alt="${esc(image.title || "concept image")}" loading="lazy">
                  <span class="concept-image-caption">${esc(image.title || "Wikimedia Commons image")}</span>
                  <span class="concept-image-credit">${esc(imageSourceLabel(image))}</span>
                </a>`;
            }).join("")}
          </div>
        </div>`;
    }

    function normalizedPhrase(value) {
      return String(value ?? "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .trim()
        .replace(/\s+/g, " ");
    }

    function phraseTokenCount(value) {
      const normalized = normalizedPhrase(value);
      return normalized ? normalized.split(" ").length : 0;
    }

    function isUsefulConceptLabel(label) {
      const value = String(label || "").trim();
      if (!value) return false;
      if (/^C\d{7}$/i.test(value)) return false;
      if (/^[A-Z]{2,12}:\S+$/.test(value)) return false;
      const normalized = normalizedPhrase(value);
      if (!normalized || normalized.length < 4) return false;
      const generic = new Set([
        "patient", "patients", "study", "result", "results", "history",
        "assessment", "plan", "procedure", "note", "clinical", "finding"
      ]);
      if (generic.has(normalized)) return false;
      return phraseTokenCount(value) >= 2 || normalized.length >= 6;
    }

    function findQuerySpans(query, phrase) {
      const rawPhrase = String(phrase || "").trim();
      if (!rawPhrase) return [];
      const spans = [];
      const queryLower = query.toLowerCase();
      const phraseLower = rawPhrase.toLowerCase();
      let direct = queryLower.indexOf(phraseLower);
      while (direct >= 0) {
        spans.push({
          start: direct,
          end: direct + rawPhrase.length,
          text: query.slice(direct, direct + rawPhrase.length)
        });
        direct = queryLower.indexOf(phraseLower, direct + 1);
      }
      const flexible = escapeRegex(rawPhrase).replace(/\\ /g, "\\s+");
      try {
        const regex = new RegExp(`(^|[^A-Za-z0-9])(${flexible})(?=$|[^A-Za-z0-9])`, "gi");
        let match;
        while ((match = regex.exec(query)) !== null) {
          const start = match.index + match[1].length;
          const end = start + match[2].length;
          if (!spans.some((span) => span.start === start && span.end === end)) {
            spans.push({
              start,
              end,
              text: query.slice(start, end)
            });
          }
          if (regex.lastIndex <= match.index) regex.lastIndex = match.index + 1;
        }
      } catch (err) {
        return spans;
      }
      return spans.sort((a, b) => a.start - b.start || b.end - a.end);
    }

    function findQuerySpan(query, phrase) {
      return findQuerySpans(query, phrase)[0] || null;
    }

    function conceptLabelCandidates(hit) {
      const values = [
        hit.matched_query_span,
        hit.matched_input,
        displayNameForHit(hit),
        hit.name,
        ...(hit.labels || [])
      ];
      const seen = new Set();
      return values
        .map((value) => String(value || "").trim())
        .filter((value) => {
          const key = normalizedPhrase(value);
          if (!key || seen.has(key) || !isUsefulConceptLabel(value)) return false;
          seen.add(key);
          return true;
        })
        .sort((a, b) => phraseTokenCount(b) - phraseTokenCount(a) || b.length - a.length);
    }

    function linkedConceptsForQuery(query, hits) {
      const candidates = [];
      (hits || []).forEach((hit, hitIndex) => {
        for (const label of conceptLabelCandidates(hit)) {
          for (const span of findQuerySpans(query, label)) {
            candidates.push({
              hit,
              hitIndex,
              cui: hit.cui,
              name: displayNameForHit(hit),
              labels: hit.labels || [],
              semanticType: semanticDisplayTypeForHit(hit),
              semanticGroup: semanticGroupForHit(hit).code,
              matchedText: span.text,
              start: span.start,
              end: span.end,
              tokenCount: phraseTokenCount(span.text),
              label
            });
          }
        }
      });
      candidates.sort((a, b) =>
        a.start - b.start
        || (b.end - b.start) - (a.end - a.start)
        || a.hitIndex - b.hitIndex
      );
      const selected = [];
      const occupied = [];
      for (const candidate of candidates) {
        const overlaps = occupied.some((span) =>
          candidate.start < span.end && span.start < candidate.end
        );
        if (overlaps) continue;
        occupied.push({ start: candidate.start, end: candidate.end });
        selected.push(candidate);
      }
      return selected.sort((a, b) => a.start - b.start);
    }

    const PREDICATE_PATTERNS = [
      { regex: /\b(no evidence of)\b/i, label: "has no evidence of", voice: "active" },
      { regex: /\b(was|were|is|are)\s+(associated with)\b/i, label: "associated with", voice: "passive" },
      { regex: /\b(was|were|is|are)\s+(notable for)\b/i, label: "notable for", voice: "passive" },
      { regex: /\b(was|were|is|are)\s+(administered|given|ordered|started|prescribed|performed|planned|scheduled|continued|increased|held|reviewed|confirmed|diagnosed|treated)\b/i, labelGroup: 2, voice: "passive" },
      { regex: /\b(treated with)\b/i, label: "treated with", voice: "active" },
      { regex: /\b(complicated by)\b/i, label: "complicated by", voice: "active" },
      { regex: /\b(concerning for|concern for)\b/i, label: "raises concern for", voice: "active" },
      { regex: /\b(due to)\b/i, label: "due to", voice: "active" },
      { regex: /\b(presenting with|presented with)\b/i, label: "presented with", voice: "active" },
      { regex: /\b(developed|develops|had|has|have|reports|reported|showed|shows|found|finds|demonstrated|demonstrates|includes|included|favored|recommended|ordered|performed|discussed|confirmed|identified|captured|measured|linked|predicted|required|excluded|denied|documented|documents|states|described|improved|worsened|persisted|reduced|increased|diagnosed|started|prescribed|administered|continued|treated|planned|scheduled|monitored|reviewed|evaluated)\b/i, labelGroup: 1, voice: "active" }
    ];
    const ACTION_PREDICATES = new Set([
      "administered", "given", "ordered", "started", "prescribed", "performed",
      "planned", "scheduled", "continued", "increased", "held", "treated"
    ]);
    const CLINICAL_ANCHOR_GROUPS = new Set(["DISO", "FIND", "PHEN"]);
    const SUBJECT_TEXT_HINTS = /\b(patient|patients|child|adult|man|woman|recipient|researcher|researchers|team|clinic|clinician|provider|providers|surgery|urology|neurology|rheumatology|cardiology|endocrinology|gynecology|ophthalmology|oncology|obstetrics|nephrology|hepatology|orthopedics|emergency department|icu)\b/i;
    const PATIENT_COHORT_TEXT_HINTS = /\b(patient|patients|child|children|adult|adolescent|man|woman|recipient|participant|participants|pregnant|postoperative|icu|cohort|trial)\b/i;
    const COHORT_TEXT_FILLER_PREFIX = /^(?:the|a|an)\s+/i;
    const COHORT_PHRASE_PATTERNS = [
      /\b((?:postoperative|pregnant|icu)\s+patient(?:\s+(?:with|at|after|in|on)\s+[^.;]{2,120})?)/gi,
      /\b((?:a|an|the)\s+(?:child|adolescent|adult|man|woman|transplant recipient)(?:\s+(?:with|at|after|in|on)\s+[^.;]{2,120})?)/gi,
      /\b((?:patients|participants)\s+(?:with|receiving|treated for|undergoing|enrolled with)\s+[^.;]{2,140}?)(?=\s+(?:versus|compared with|with patients|and patients)\b|[.;]|$)/gi
    ];
    const CONCATENATION_BRIDGE_TOKENS = new Set([
      "with", "without", "of", "to", "due", "secondary", "associated",
      "related", "from", "in", "for", "type", "stage", "grade", "acute",
      "chronic", "left", "right", "lower", "upper", "reduced", "preserved",
      "elevated", "low", "high", "positive", "negative", "severe", "moderate",
      "mild", "resistant", "sensitive", "suspected", "confirmed"
    ]);
    const CONCATENATION_GROUPS = new Set([
      "ANAT", "DISO", "FIND", "GENE", "LIVB", "PHEN", "PHYS", "PROC"
    ]);

    function predicateTextForMatch(query, pattern, match) {
      let text = pattern.label || String(match[pattern.labelGroup || 0] || match[0] || "").toLowerCase();
      const after = query.slice(match.index + match[0].length, match.index + match[0].length + 40).toLowerCase();
      if (ACTION_PREDICATES.has(text) && /^\s+before\b/.test(after)) text = `${text} before`;
      if (ACTION_PREDICATES.has(text) && /^\s+after\b/.test(after)) text = `${text} after`;
      if (ACTION_PREDICATES.has(text) && /^\s+for\b/.test(after)) text = `${text} for`;
      return text;
    }

    function predicateMatchesForQuery(query) {
      const candidates = [];
      for (const pattern of PREDICATE_PATTERNS) {
        const flags = pattern.regex.flags.includes("g") ? pattern.regex.flags : `${pattern.regex.flags}g`;
        const regex = new RegExp(pattern.regex.source, flags);
        let match;
        while ((match = regex.exec(query)) !== null) {
          candidates.push({
            text: predicateTextForMatch(query, pattern, match),
            start: match.index,
            end: match.index + match[0].length,
            voice: pattern.voice || "active"
          });
          if (regex.lastIndex <= match.index) regex.lastIndex = match.index + 1;
        }
      }
      candidates.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
      const selected = [];
      for (const candidate of candidates) {
        if (selected.some((item) => candidate.start < item.end && item.start < candidate.end)) continue;
        selected.push(candidate);
      }
      return selected.sort((a, b) => a.start - b.start || a.end - b.end);
    }

    function sentenceSpans(query) {
      const spans = [];
      let start = 0;
      const regex = /[.!?]+(?=\s+|$)/g;
      let match;
      while ((match = regex.exec(query)) !== null) {
        const end = match.index + match[0].length;
        if (query.slice(start, end).trim()) spans.push({ start, end });
        start = end;
        while (start < query.length && /\s/.test(query[start])) start += 1;
      }
      if (query.slice(start).trim()) spans.push({ start, end: query.length });
      return spans.length ? spans : [{ start: 0, end: query.length }];
    }

    function spanForPosition(spans, position) {
      return spans.find((span) => position >= span.start && position <= span.end) || spans[0];
    }

    function lastClauseBoundary(query, from, to) {
      const segment = query.slice(from, to);
      let boundary = from;
      const regex = /(?:[;,]\s*|\s+(?:and|but|then)\s+)/gi;
      let match;
      while ((match = regex.exec(segment)) !== null) {
        boundary = from + match.index + match[0].length;
      }
      return boundary;
    }

    function nextClauseBoundary(query, from, to) {
      const segment = query.slice(from, to);
      const match = /(?:[;,]\s*|\s+(?:and|but|then)\s+)/i.exec(segment);
      return match ? from + match.index : to;
    }

    function predicateScope(query, predicate, predicates, sentence) {
      let start = sentence.start;
      let end = sentence.end;
      const previous = predicates.filter((item) =>
        item.end <= predicate.start && item.start >= sentence.start && item.end <= sentence.end
      ).pop();
      const next = predicates.find((item) =>
        item.start >= predicate.end && item.start >= sentence.start && item.start <= sentence.end
      );
      if (previous) start = Math.max(start, lastClauseBoundary(query, previous.end, predicate.start));
      if (next) end = Math.min(end, nextClauseBoundary(query, predicate.end, next.start));
      return { start, end };
    }

    function cleanPlainRoleText(value, fallback) {
      const cleaned = String(value || "")
        .replace(/^[\s,.;:]+|[\s,.;:]+$/g, "")
        .replace(/^(the|a|an)\s+/i, "")
        .trim();
      return cleaned || fallback;
    }

    function conceptBefore(concepts, position, start = 0) {
      const eligible = concepts.filter((concept) =>
        (position < 0 || concept.end <= position) && concept.start >= start
      );
      return eligible.length ? eligible[eligible.length - 1] : null;
    }

    function conceptAfter(concepts, position, end = Number.POSITIVE_INFINITY) {
      return concepts.find((concept) =>
        (position < 0 || concept.start >= position) && concept.end <= end
      ) || null;
    }

    function conceptsInRange(concepts, start, end) {
      return concepts.filter((concept) => concept.start >= start && concept.end <= end);
    }

    function isClinicalAnchorConcept(concept) {
      const group = String(concept?.semanticGroup || "");
      const type = String(concept?.semanticType || "").toLowerCase();
      return CLINICAL_ANCHOR_GROUPS.has(group)
        || /disease|syndrome|finding|symptom|pathologic|injury|mental|behavioral/.test(type);
    }

    function isDrugOrChemicalConcept(concept) {
      const group = String(concept?.semanticGroup || "");
      const type = String(concept?.semanticType || "").toLowerCase();
      return group === "CHEM" || /drug|chemical|pharmacologic|vitamin|antibiotic|hormone/.test(type);
    }

    function entityKey(entity) {
      if (!entity) return "";
      if (entity.kind === "concept") return `concept:${entity.concept?.cui || ""}:${entity.concept?.start || 0}`;
      return `text:${normalizedPhrase(entity.text || "")}`;
    }

    function conceptEntity(concept) {
      return { kind: "concept", concept };
    }

    function textEntity(text, fallback) {
      return { kind: "text", text: cleanPlainRoleText(text, fallback) };
    }

    function statementKey(statement) {
      return [
        entityKey(statement.subject),
        normalizedPhrase(statement.predicate),
        entityKey(statement.object)
      ].join("|");
    }

    function nearestClinicalAnchorBefore(concepts, position) {
      const anchors = concepts
        .filter((concept) => concept.end <= position && isClinicalAnchorConcept(concept));
      return anchors.length ? anchors[anchors.length - 1] : null;
    }

    function subjectEntitiesForPredicate(query, concepts, predicate, scope) {
      const beforeConcepts = conceptsInRange(concepts, scope.start, predicate.start);
      const rawSubject = query.slice(scope.start, predicate.start);
      if (predicate.voice === "passive") {
        const closeSubjects = beforeConcepts.filter((concept) => predicate.start - concept.end <= 80);
        if (closeSubjects.length) {
          const last = closeSubjects[closeSubjects.length - 1];
          const sameKind = closeSubjects.filter((concept) =>
            concept.semanticGroup === last.semanticGroup && predicate.start - concept.end <= 80
          );
          return sameKind.slice(-3).map((concept) => conceptEntity(concept));
        }
      }
      if (SUBJECT_TEXT_HINTS.test(rawSubject)) return [textEntity(rawSubject, "patient")];
      const concept = beforeConcepts.length ? beforeConcepts[beforeConcepts.length - 1] : null;
      if (concept) return [conceptEntity(concept)];
      return [textEntity(rawSubject, "sentence")];
    }

    function objectEntityForPredicate(query, concepts, predicate, scope, subject) {
      const afterConcept = conceptAfter(concepts, predicate.end, scope.end);
      const predicateBase = normalizedPhrase(predicate.text).split(" ")[0] || predicate.text;
      if (afterConcept) return conceptEntity(afterConcept);
      if (ACTION_PREDICATES.has(predicateBase) && subject?.kind === "concept" && isDrugOrChemicalConcept(subject.concept)) {
        const anchor = nearestClinicalAnchorBefore(concepts, predicate.start);
        if (anchor) return conceptEntity(anchor);
        return textEntity("patient", "patient");
      }
      return textEntity(query.slice(predicate.end, scope.end), "not detected");
    }

    function qualifierRoleForConcept(query, concept) {
      const before = query.slice(Math.max(0, concept.start - 48), concept.start).toLowerCase();
      if (/(during|while|when|after|before)\s+$/.test(before)) return "time/context";
      if (/(because of|due to)\s+$/.test(before)) return "reason";
      if (/(treated with|receiving|starting|started|on)\s+$/.test(before)) return "treatment";
      if (/(using|with|on)\s+$/.test(before)) return "method/context";
      if (/for\s+$/.test(before)) return "purpose";
      if (/(in|among)\s+$/.test(before)) return "population/context";
      return "";
    }

    function statementQualifiers(query, concepts, scope, subject, object) {
      const used = new Set([entityKey(subject), entityKey(object)]);
      return conceptsInRange(concepts, scope.start, scope.end)
        .filter((concept) => !used.has(entityKey(conceptEntity(concept))))
        .map((concept) => ({
          role: qualifierRoleForConcept(query, concept),
          kind: "concept",
          concept
        }))
        .filter((qualifier) => qualifier.role);
    }

    function addStatement(statements, seen, statement) {
      if (!statement?.subject || !statement?.object || !statement.predicate) return;
      const key = statementKey(statement);
      if (seen.has(key)) return;
      seen.add(key);
      statements.push(statement);
    }

    function associatedStatementsForPredicate(query, concepts, statement, scope) {
      if (statement.object?.kind !== "concept") return [];
      if (!isClinicalAnchorConcept(statement.object.concept)) return [];
      const anchor = statement.object.concept;
      const trailing = conceptsInRange(concepts, anchor.end, scope.end)
        .filter((concept) => concept.cui !== anchor.cui && isClinicalAnchorConcept(concept));
      return trailing.map((concept) => {
        const bridge = query.slice(anchor.end, concept.start).toLowerCase();
        let predicate = "has associated finding";
        if (/\b(concerning for|concern for)\b/.test(bridge)) predicate = "raises concern for";
        return {
          subject: conceptEntity(anchor),
          predicate,
          object: conceptEntity(concept),
          qualifiers: [],
          start: anchor.start,
          end: concept.end
        };
      });
    }

    function buildStructuredStatement(query, hits) {
      const concepts = linkedConceptsForQuery(query, hits);
      const sentences = sentenceSpans(query);
      const predicates = predicateMatchesForQuery(query);
      const statements = [];
      const seen = new Set();

      for (const predicate of predicates) {
        const sentence = spanForPosition(sentences, predicate.start);
        const scope = predicateScope(query, predicate, predicates, sentence);
        const subjects = subjectEntitiesForPredicate(query, concepts, predicate, scope);
        for (const subject of subjects) {
          const object = objectEntityForPredicate(query, concepts, predicate, scope, subject);
          const statement = {
            subject,
            predicate: predicate.text,
            object,
            qualifiers: statementQualifiers(query, concepts, scope, subject, object),
            start: scope.start,
            end: scope.end
          };
          addStatement(statements, seen, statement);
          for (const associated of associatedStatementsForPredicate(query, concepts, statement, scope)) {
            addStatement(statements, seen, associated);
          }
        }
      }

      const represented = new Set();
      for (const statement of statements) {
        for (const entity of [statement.subject, statement.object, ...(statement.qualifiers || [])]) {
          if (entity?.kind === "concept") represented.add(`${entity.concept.cui}:${entity.concept.start}:${entity.concept.end}`);
        }
      }
      const otherConcepts = concepts.filter((concept) =>
        !represented.has(`${concept.cui}:${concept.start}:${concept.end}`)
      );

      return {
        query,
        statements: statements.slice(0, 14),
        hasStructuredStatement: statements.length > 0,
        otherConcepts,
        linkedConcepts: concepts
      };
    }

    function renderStatementEntity(entity) {
      if (!entity) return '<span class="muted">not detected</span>';
      if (entity.kind === "concept") {
        const concept = entity.concept;
        const displayText = concept.matchedText || concept.name || concept.cui;
        const titleParts = [concept.name, concept.cui, concept.semanticType]
          .filter(Boolean)
          .join(" · ");
        return `
          <a class="statement-concept" href="${esc(utsConceptUrl(concept.cui))}" target="_blank" rel="noreferrer" title="${esc(titleParts || displayText)}">
            <span class="statement-concept-name">${esc(displayText)}</span>
            <span class="statement-concept-cui mono">${esc(concept.cui)}</span>
          </a>`;
      }
      return `<span class="statement-text">${esc(entity.text || "")}</span>`;
    }

    function renderQualifier(qualifier) {
      return `
        <div class="statement-qualifier">
          <span class="statement-qualifier-role">${esc(qualifier.role || "context")}</span>
          ${renderStatementEntity(qualifier)}
        </div>`;
    }

    function renderStatementTriple(statement, index) {
      return `
        <div class="statement-card">
          <div class="statement-card-index">${fmtNum(index + 1)}</div>
          <div class="statement-grid" aria-label="Structured statement ${fmtNum(index + 1)}">
            <div class="statement-slot">
              <div class="statement-slot-label">Subject</div>
              <div class="statement-slot-value">${renderStatementEntity(statement.subject)}</div>
            </div>
            <div class="statement-slot">
              <div class="statement-slot-label">Predicate</div>
              <div class="statement-slot-value statement-predicate">${esc(statement.predicate)}</div>
            </div>
            <div class="statement-slot">
              <div class="statement-slot-label">Object</div>
              <div class="statement-slot-value">${renderStatementEntity(statement.object)}</div>
            </div>
            <div class="statement-slot statement-slot-qualifiers">
              <div class="statement-slot-label">Qualifiers</div>
              <div class="statement-slot-value statement-qualifiers">
                ${(statement.qualifiers || []).length
                  ? statement.qualifiers.map((qualifier) => renderQualifier(qualifier)).join("")
                  : '<span class="muted">none</span>'}
              </div>
            </div>
          </div>
        </div>`;
    }

    function conceptGroupsCanConcatenate(previous, current) {
      const previousGroup = String(previous?.semanticGroup || "");
      const currentGroup = String(current?.semanticGroup || "");
      if (!previousGroup || !currentGroup) return false;
      if (previousGroup === "CHEM" || currentGroup === "CHEM") {
        return previousGroup === "CHEM" && currentGroup === "CHEM";
      }
      return CONCATENATION_GROUPS.has(previousGroup) && CONCATENATION_GROUPS.has(currentGroup);
    }

    function bridgeCanConcatenate(bridge) {
      if (/[.;:!?]/.test(bridge || "")) return false;
      const tokens = normalizedPhrase(bridge).split(" ").filter(Boolean);
      if (!tokens.length) return true;
      if (tokens.length > 5) return false;
      return tokens.every((token) =>
        CONCATENATION_BRIDGE_TOKENS.has(token) || /^\d+$/.test(token)
      );
    }

    function conceptsShouldConcatenate(query, previous, current) {
      if (!previous || !current || previous.cui === current.cui) return false;
      if (current.start < previous.end) return false;
      if (current.start - previous.end > 48) return false;
      if (!conceptGroupsCanConcatenate(previous, current)) return false;
      const bridge = query.slice(previous.end, current.start);
      return bridgeCanConcatenate(bridge);
    }

    function renderConcatenationBridge(bridge) {
      const hasText = normalizedPhrase(bridge).length > 0;
      const className = hasText
        ? "statement-concat-bridge"
        : "statement-concat-bridge statement-concat-bridge-empty";
      return `<span class="${className}" title="These adjacent concepts can be read as one combined expression">${hasText ? esc(bridge) : ""}</span>`;
    }

    function renderLinkedSentence(statement) {
      const concepts = statement.linkedConcepts || [];
      if (!concepts.length) return esc(statement.query);
      let cursor = 0;
      const pieces = [];
      let previousConcept = null;
      for (const concept of concepts) {
        const bridge = statement.query.slice(cursor, concept.start);
        if (previousConcept && conceptsShouldConcatenate(statement.query, previousConcept, concept)) {
          pieces.push(renderConcatenationBridge(bridge));
        } else {
          pieces.push(esc(bridge));
        }
        const displayText = concept.matchedText || statement.query.slice(concept.start, concept.end);
        const titleParts = [concept.name, concept.cui, concept.semanticType]
          .filter(Boolean)
          .join(" · ");
        pieces.push(`
          <a class="statement-inline-concept" href="${esc(utsConceptUrl(concept.cui))}" target="_blank" rel="noreferrer" title="${esc(titleParts || displayText)}">
            ${esc(displayText)}
          </a>`);
        cursor = concept.end;
        previousConcept = concept;
      }
      pieces.push(esc(statement.query.slice(cursor)));
      return pieces.join("");
    }

    function linkedConceptsHaveConcatenation(statement) {
      const concepts = statement?.linkedConcepts || [];
      for (let index = 1; index < concepts.length; index += 1) {
        if (conceptsShouldConcatenate(statement.query || "", concepts[index - 1], concepts[index])) {
          return true;
        }
      }
      return false;
    }

    function cleanCohortText(value) {
      const cleaned = String(value || "")
        .replace(/^[\s,.;:]+|[\s,.;:]+$/g, "")
        .replace(COHORT_TEXT_FILLER_PREFIX, "")
        .replace(/\s+/g, " ")
        .trim();
      if (cleaned.length <= 170) return cleaned;
      return `${cleaned.slice(0, 167).replace(/\s+\S*$/, "")}...`;
    }

    function cohortTypeForText(value) {
      const text = normalizedPhrase(value);
      if (/\b(cohort|trial|participant|participants|enrolled)\b/.test(text)) return "Research cohort";
      if (/\b(pregnant|weeks|obstetrics)\b/.test(text)) return "Pregnancy cohort";
      if (/\b(icu|emergency|postoperative|transplant|recipient)\b/.test(text)) return "Care setting";
      if (/\b(child|children|adolescent|adult|man|woman)\b/.test(text)) return "Demographic cohort";
      return "Patient group";
    }

    function cohortSpanForText(query, text) {
      const direct = findQuerySpan(query, text);
      if (direct) return direct;
      const withoutArticle = cleanCohortText(text);
      return findQuerySpan(query, withoutArticle);
    }

    function conceptsForCohortSpan(concepts, span, description) {
      const normalizedDescription = normalizedPhrase(description);
      return (concepts || []).filter((concept) => {
        if (span && concept.start >= span.start && concept.end <= span.end) return true;
        const matched = normalizedPhrase(concept.matchedText || concept.name || "");
        return matched && normalizedDescription.includes(matched);
      }).slice(0, 8);
    }

    function addCohortItem(items, seen, query, concepts, text, source) {
      const description = cleanCohortText(text);
      if (!description || !PATIENT_COHORT_TEXT_HINTS.test(description)) return;
      const key = normalizedPhrase(description);
      if (!key || seen.has(key)) return;
      seen.add(key);
      const span = cohortSpanForText(query, text) || cohortSpanForText(query, description);
      items.push({
        description,
        source,
        type: cohortTypeForText(description),
        concepts: conceptsForCohortSpan(concepts, span, description)
      });
    }

    function buildPatientCohort(query, statement) {
      const concepts = statement?.linkedConcepts || [];
      const items = [];
      const seen = new Set();
      for (const item of statement?.statements || []) {
        if (item.subject?.kind !== "text") continue;
        addCohortItem(items, seen, query, concepts, item.subject.text, "statement subject");
      }
      for (const pattern of COHORT_PHRASE_PATTERNS) {
        const regex = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
        let match;
        while ((match = regex.exec(query)) !== null) {
          addCohortItem(items, seen, query, concepts, match[1] || match[0], "text pattern");
          if (regex.lastIndex <= match.index) regex.lastIndex = match.index + 1;
        }
      }
      return {
        items: items.slice(0, 4)
      };
    }

    function renderCohortConceptChip(concept) {
      const label = concept.matchedText || concept.name || concept.cui;
      const titleParts = [concept.name, concept.cui, concept.semanticType]
        .filter(Boolean)
        .join(" · ");
      return `
        <a class="chip cohort-concept-chip" href="${esc(utsConceptUrl(concept.cui))}" target="_blank" rel="noreferrer" title="${esc(titleParts || label)}">
          ${esc(label)}
        </a>`;
    }

    function renderCohortItem(item) {
      return `
        <div class="cohort-item">
          <div class="cohort-item-main">
            <div class="cohort-item-title">${esc(item.description)}</div>
            <div class="result-semantic-type">${esc(item.type)}</div>
          </div>
          <div class="chips cohort-concept-chips">
            ${(item.concepts || []).length
              ? item.concepts.map(renderCohortConceptChip).join("")
              : '<span class="chip">no linked CUI in cohort phrase</span>'}
          </div>
        </div>`;
    }

    function renderPatientCohortGroup(cohort) {
      const items = cohort?.items || [];
      if (!items.length) return "";
      return `
        <section class="result-group cohort-group" aria-label="Patient cohort">
          <div class="result-group-head">
            <div>
              <span class="result-group-title">Patient Cohort</span>
              <span class="result-group-code">COHORT</span>
            </div>
            <div class="result-group-count">${fmtNum(items.length)} inferred ${items.length === 1 ? "group" : "groups"}</div>
          </div>
          <div class="result-group-items cohort-group-items">
            ${items.map(renderCohortItem).join("")}
          </div>
        </section>`;
    }

    function renderStructuredStatementPanel(statement) {
      const hasStructuredStatement = Boolean(statement?.hasStructuredStatement);
      const hasConcatenation = linkedConceptsHaveConcatenation(statement);
      if (!hasStructuredStatement && !hasConcatenation) return "";
      const conceptCount = statement.linkedConcepts?.length || 0;
      return `
        <div class="statement-panel result-statement-panel">
          <div class="statement-panel-head">
            <h2>Linked Statement</h2>
            <div class="muted small">${fmtNum(conceptCount)} linked ${conceptCount === 1 ? "concept" : "concepts"}</div>
          </div>
          <div class="statement-linked-sentence">${renderLinkedSentence(statement)}</div>
        </div>`;
    }

    function semanticResultBuckets(hits) {
      if ((state.lastSemanticResultBuckets || []).length) {
        return semanticResultBucketsFromPrecomputed(state.lastSemanticResultBuckets, hits);
      }
      const assignedCuis = new Set();
      return activeSemanticResultBucketDefs().map((bucket) => {
        const matches = [];
        hits.forEach((hit, index) => {
          if (!hitClearsSemanticBucketRelevance(hit)) return;
          const hitKey = String(hit.cui || hit.doc_id || index);
          if (assignedCuis.has(hitKey)) return;
          if (hitMatchesSemanticBucket(hit, bucket)) {
            matches.push({ kind: "hit", hit, rank: index + 1 });
            assignedCuis.add(hitKey);
          }
        });
        const bestRelevance = matches.reduce((best, item) => Math.max(best, hitRelevanceScore(item.hit)), 0);
        return {
          ...bucket,
          total: matches.length,
          relatedTotal: 0,
          bestRelevance,
          items: matches
        };
      }).filter((group) => group.items.length)
        .sort(compareResultGroupsByRelevance);
    }

    function semanticResultBucketsFromPrecomputed(precomputedGroups, hits) {
      const hitLookup = precomputedBucketHitLookup(hits);
      const precomputedByKey = new Map(
        (precomputedGroups || [])
          .filter((group) => group && group.key)
          .map((group) => [String(group.key), group])
      );
      const assignedCuis = new Set();
      return activeSemanticResultBucketDefs().map((bucketDef) => {
        const precomputed = precomputedByKey.get(bucketDef.key) || {};
        const bucket = { ...bucketDef, ...precomputed };
        const hitItems = [];
        for (const item of precomputed.items || []) {
          if (item.kind !== "hit") continue;
          const hit = precomputedBucketHit(item, hitLookup);
          if (!hit) continue;
          if (!hitClearsSemanticBucketRelevance(hit)) continue;
          const hitKey = String(hit.cui || hit.doc_id || "");
          if (!hitKey || assignedCuis.has(hitKey)) continue;
          hitItems.push({
            kind: "hit",
            hit,
            rank: Number(item.rank) || (hitItems.length + 1)
          });
          assignedCuis.add(hitKey);
        }
        const bestRelevance = Number.isFinite(Number(precomputed.bestRelevance))
          ? Number(precomputed.bestRelevance)
          : hitItems.reduce((best, item) => Math.max(best, hitRelevanceScore(item.hit)), 0);
        return {
          ...bucket,
          total: Number.isFinite(Number(precomputed.total)) ? Number(precomputed.total) : hitItems.length,
          relatedTotal: 0,
          bestRelevance,
          items: hitItems
        };
      }).filter((group) => group.items.length)
        .sort(compareResultGroupsByRelevance);
    }

    function precomputedBucketHitLookup(hits) {
      const byDocId = new Map();
      const byCui = new Map();
      (hits || []).forEach((hit) => {
        const docId = String(hit.doc_id || "");
        const cui = String(hit.cui || "");
        if (docId) byDocId.set(docId, hit);
        if (cui && !byCui.has(cui)) byCui.set(cui, hit);
      });
      return { byDocId, byCui };
    }

    function precomputedBucketHit(item, lookup) {
      const docId = String(item.doc_id || "");
      const cui = String(item.cui || "");
      if (docId && lookup.byDocId.has(docId)) return lookup.byDocId.get(docId);
      if (cui && lookup.byCui.has(cui)) return lookup.byCui.get(cui);
      return null;
    }

    function relatedSemanticBucketItems(bucket, assignedCuis, limit) {
      if (limit <= 0) return { total: 0, items: [] };
      const items = [];
      let total = 0;
      for (const view of state.lastSemanticGroupViews || []) {
        const groupCode = String(view.semantic_group || "").trim();
        for (const relation of view.items || []) {
          if (!relationVisibleInSemanticBucket(relation, bucket, groupCode)) continue;
          if (!relationClearsRelatedBucketEvidence(relation)) continue;
          const key = String(relation.cui || relation.label || "");
          if (!key || assignedCuis.has(key)) continue;
          total += 1;
          if (items.length < limit) {
            assignedCuis.add(key);
            items.push({ kind: "relation", relation });
          }
        }
      }
      return { total, items };
    }

    function relatedResultBuckets() {
      if (!state.includeRelated) return [];
      if ((state.lastRelatedResultBuckets || []).length) {
        return relatedResultBucketsFromPrecomputed(state.lastRelatedResultBuckets, state.lastResults);
      }
      const assignedCuis = new Set();
      return activeSemanticResultBucketDefs().map((bucket) => {
        const related = relatedSemanticBucketItems(bucket, assignedCuis, Number.POSITIVE_INFINITY);
        const inferredItems = inferredRelatedSemanticBucketItems(bucket, state.lastResults, assignedCuis);
        const items = [...related.items, ...inferredItems];
        const bestRelevance = related.items.reduce((best, item) => {
          const [strength, confidence] = relationStrengthConfidence(item.relation || {});
          return Math.max(best, strength, confidence);
        }, 0);
        return {
          ...bucket,
          total: 0,
          relatedTotal: related.total + inferredItems.length,
          bestRelevance: items.reduce((best, item) => {
            const [strength, confidence] = relationStrengthConfidence(item.relation || {});
            return Math.max(best, strength, confidence);
          }, bestRelevance),
          items
        };
      }).filter((group) => group.items.length)
        .sort(compareResultGroupsByRelevance);
    }

    function resultItemKey(item) {
      if (item?.kind === "relation") {
        const relation = item.relation || {};
        return String(relation.cui || relation.label || "").trim();
      }
      const hit = item?.hit || {};
      return String(hit.cui || hit.doc_id || "").trim();
    }

    function mergeRelatedIntoResultBuckets(hitGroups, relatedGroups) {
      const groups = (hitGroups || []).map((group) => ({
        ...group,
        items: [...(group.items || [])],
        total: Number(group.total || 0),
        relatedTotal: Number(group.relatedTotal || 0),
        bestRelevance: Number(group.bestRelevance || 0)
      }));
      const byKey = new Map(groups.map((group) => [String(group.key || ""), group]));
      const assigned = new Set(
        groups.flatMap((group) => (group.items || []).map(resultItemKey).filter(Boolean))
      );
      for (const relatedGroup of relatedGroups || []) {
        const key = String(relatedGroup.key || "").trim();
        if (!key) continue;
        let group = byKey.get(key);
        if (!group) {
          group = {
            ...relatedGroup,
            items: [],
            total: 0,
            relatedTotal: 0,
            bestRelevance: Number(relatedGroup.bestRelevance || 0)
          };
          byKey.set(key, group);
          groups.push(group);
        }
        let added = 0;
        for (const item of relatedGroup.items || []) {
          const itemKey = resultItemKey(item);
          if (!itemKey || assigned.has(itemKey)) continue;
          assigned.add(itemKey);
          group.items.push(item);
          added += 1;
        }
        group.relatedTotal = Number(group.relatedTotal || 0) + added;
        group.bestRelevance = Math.max(
          Number(group.bestRelevance || 0),
          Number(relatedGroup.bestRelevance || 0)
        );
      }
      return groups.filter((group) => (group.items || []).length)
        .sort(compareResultGroupsByRelevance);
    }

    function relatedResultBucketsFromPrecomputed(precomputedGroups, hits) {
      const precomputedByKey = new Map(
        (precomputedGroups || [])
          .filter((group) => group && group.key)
          .map((group) => [String(group.key), group])
      );
      const assignedCuis = new Set();
      return activeSemanticResultBucketDefs().map((bucketDef) => {
        const precomputed = precomputedByKey.get(bucketDef.key) || {};
        const bucket = { ...bucketDef, ...precomputed };
        const items = [];
        for (const item of precomputed.items || []) {
          const relation = item.relation || item;
          if (!relationClearsRelatedBucketEvidence(relation)) continue;
          const key = String(relation.cui || relation.label || "");
          if (!key || assignedCuis.has(key)) continue;
          assignedCuis.add(key);
          items.push({ kind: "relation", relation });
        }
        items.push(...inferredRelatedSemanticBucketItems(bucket, hits, assignedCuis));
        const computedBestRelevance = items.reduce((best, item) => {
            const [strength, confidence] = relationStrengthConfidence(item.relation || {});
            return Math.max(best, strength, confidence);
          }, 0);
        const bestRelevance = Number.isFinite(Number(precomputed.bestRelevance))
          ? Math.max(Number(precomputed.bestRelevance), computedBestRelevance)
          : computedBestRelevance;
        return {
          ...bucket,
          total: 0,
          relatedTotal: items.length,
          bestRelevance,
          items
        };
      }).filter((group) => group.items.length)
        .sort(compareResultGroupsByRelevance);
    }

    function inferredRelatedSemanticBucketItems(bucket, hits, assignedCuis) {
      if (!semanticExpansionProfiles.length) return [];
      const text = semanticExpansionContextText(hits);
      const items = [];
      const seen = new Set();
      for (const profile of semanticExpansionProfiles) {
        if (!profileMatchesBucket(profile, bucket)) continue;
        if (!profile.triggerPatterns.some((pattern) => pattern.test(text))) continue;
        for (const item of profile.items) {
          const key = String(item.cui || "");
          if (!key || assignedCuis.has(key) || seen.has(key)) continue;
          const relation = {
            ...item,
            semantic_group: item.semantic_group || profile.target_group || bucket.code || "",
            semantic_group_label: item.semantic_group_label || bucket.label || "",
            relation_group: "semantic expansion",
            relation: "RO",
            rela: "profile_expansion",
            source: "semantic expansion profile",
            source_name: profile.source,
            source_rank: profile.source_rank || 0,
            edge: {
              type: "associated_with",
              strength: 0.74,
              strength_metric: "curated_profile_score",
              directionality: "bidirectional",
              evidence: {
                method: "curated",
                provenance: "semantic_expansion_profile"
              },
              context: {
                profile_id: profile.id || profile.source || "",
                trigger_context: "query_or_top_result_label"
              },
              confidence: 0.64
            }
          };
          if (!relationClearsRelatedBucketEvidence(relation)) continue;
          seen.add(key);
          assignedCuis.add(key);
          items.push({ kind: "relation", relation });
        }
      }
      return items;
    }

    function semanticExpansionContextText(hits) {
      return [
        state.lastQuery || "",
        ...hits.slice(0, 12).flatMap((hit) => [hit.name || "", ...(hit.labels || [])])
      ].join(" ");
    }

    function profileMatchesBucket(profile, bucket) {
      if (profile.target_bucket && profile.target_bucket === bucket.key) return true;
      if (profile.target_group && bucket.code && profile.target_group === bucket.code) return true;
      return false;
    }

    function bucketPreferredOrder(group) {
      const key = String(group.key || "");
      const index = semanticResultBucketDefs.findIndex((bucket) => bucket.key === key);
      return index < 0 ? semanticResultBucketDefs.length : index;
    }

    function compareResultGroupsByRelevance(a, b) {
      const scoreDelta = Number(b.bestRelevance || 0) - Number(a.bestRelevance || 0);
      if (Math.abs(scoreDelta) > 0.000001) return scoreDelta;
      return bucketPreferredOrder(a) - bucketPreferredOrder(b);
    }

    function hitRelevanceScore(hit) {
      const breakdown = hit?.score_breakdown || {};
      const value = breakdown.rank_score ?? hit?.rank_score ?? hit?.score ?? 0;
      const score = Number(value);
      return Number.isFinite(score) ? score : 0;
    }

    function hitClearsSemanticBucketRelevance(hit) {
      return hitRelevanceScore(hit) >= SEMANTIC_BUCKET_MIN_RELEVANCE;
    }

    function relationStrengthConfidence(relation) {
      const edge = relation?.edge || {};
      const strength = Number(edge.strength ?? relation?.strength ?? relation?.score ?? relation?.similarity ?? 0);
      const confidence = Number(edge.confidence ?? relation?.confidence ?? 0);
      const cleanStrength = Number.isFinite(strength) ? strength : 0;
      let cleanConfidence = Number.isFinite(confidence) ? confidence : 0;
      if (cleanConfidence <= 0 && cleanStrength >= 0.75) cleanConfidence = 0.50;
      return [cleanStrength, cleanConfidence];
    }

    function relationClearsRelatedBucketEvidence(relation) {
      const [strength, confidence] = relationStrengthConfidence(relation);
      return strength >= RELATED_BUCKET_MIN_STRENGTH && confidence >= RELATED_BUCKET_MIN_CONFIDENCE;
    }

    function resultCountLabel(count) {
      return `${fmtNum(count)} ${count === 1 ? "result" : "results"}`;
    }

    function resultShownLabel(group) {
      if (!group.total && !group.relatedTotal) return "0 returned";
      if (!group.relatedTotal) return `${fmtNum(group.items.length)} of ${fmtNum(group.total)} returned`;
      return `${fmtNum(group.total)} returned · ${fmtNum(group.relatedTotal)} related`;
    }

    function renderResultBucket(group) {
      const hasOverflow = group.items.length > 4;
      return `
        <section class="result-group${hasOverflow ? " result-group-scrollable" : ""}" aria-label="${esc(group.label)} results">
          <div class="result-group-head">
            <div>
              <span class="result-group-title">${esc(group.label)}</span>
              <span class="result-group-code">${esc(group.code)}</span>
            </div>
            <div class="result-group-count">${esc(resultShownLabel(group))}</div>
          </div>
          <div class="result-group-items"${hasOverflow ? ' tabindex="0"' : ""}>
            ${group.items.map((item) => item.kind === "relation"
              ? renderCompactRelatedSuggestionCard(item.relation)
              : renderCompactResultCard(item.hit, item.rank)
            ).join("")}
          </div>
        </section>`;
    }

    function renderRelatedResultBucket(group) {
      const hasOverflow = group.items.length > 4;
      return `
        <section class="result-group result-group-related${hasOverflow ? " result-group-scrollable" : ""}" aria-label="${esc(group.label)} related results">
          <div class="result-group-head">
            <div>
              <span class="result-group-title">${esc(group.label)}</span>
              <span class="result-group-code">related</span>
            </div>
            <div class="result-group-count">${fmtNum(group.items.length)} related</div>
          </div>
          <div class="result-group-items"${hasOverflow ? ' tabindex="0"' : ""}>
            ${group.items.map((item) => renderCompactRelatedSuggestionCard(item.relation)).join("")}
          </div>
        </section>`;
    }

    function renderCompactRelatedSuggestionCard(item) {
      const label = item.label || item.cui || "Related concept";
      const sourceText = item.source_name
        ? (item.source_rank ? `from #${fmtNum(item.source_rank)} ${item.source_name}` : `from ${item.source_name}`)
        : "related";
      return `
        <div class="result result-compact result-related-suggestion">
          <details class="result-details compact-card-details">
            <summary class="compact-result-summary">
              <button type="button" class="related-concept compact-result-title related-suggestion-title" data-query="${esc(label)}" title="${esc(label)}">
                ${esc(label)}
              </button>
              <span class="result-semantic-type related-result-type">
                <span class="related-marker">Related</span>
                <span>${esc(item.semantic_type || item.semantic_group_label || "related")}</span>
              </span>
              <span class="compact-details-label">Details</span>
            </summary>
            <div class="compact-details-body">
              <div class="detail-section">
                <div class="detail-title">Related Concept Metadata</div>
                <div class="chips">
                  <span class="chip">rank ${fmtNum(item.source_rank || 0)}</span>
                  <span class="chip mono">${esc(item.cui || "")}</span>
                  <span class="chip">related</span>
                  <span class="chip">${esc(item.relation_group ? item.relation_group.replaceAll("_", " ") : "MRREL")}</span>
                  <span class="chip">${esc(sourceText)}</span>
                  ${item.source ? `<span class="chip">${esc(item.source)}</span>` : ""}
                  ${renderUniversalEdgeChips(item)}
                </div>
              </div>
            </div>
          </details>
        </div>`;
    }

    function fmtEdgeScore(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "";
      return number.toFixed(2);
    }

    function renderUniversalEdgeChips(item) {
      const edge = item.edge || {};
      if (!edge.type) return "";
      const evidence = edge.evidence || {};
      const chips = [
        `type ${edge.type}`,
        edge.directionality ? `direction ${edge.directionality}` : "",
        fmtEdgeScore(edge.strength) ? `strength ${fmtEdgeScore(edge.strength)}` : "",
        fmtEdgeScore(edge.confidence) ? `confidence ${fmtEdgeScore(edge.confidence)}` : "",
        evidence.method ? `method ${evidence.method}` : "",
        evidence.provenance ? `provenance ${evidence.provenance}` : ""
      ].filter(Boolean);
      return chips.map((chip) => `<span class="chip">${esc(chip.replaceAll("_", " "))}</span>`).join("");
    }

    function compactSignalSummary(hit) {
      const positive = signalContributionItems(hit).slice(0, 2).map((item) =>
        `<span class="compact-signal-chip">${esc(item.label)} ${fmtScore(item.value)}</span>`
      );
      const deductions = signalDeductionItems(hit).slice(0, 1).map((item) =>
        `<span class="compact-signal-chip compact-signal-chip-deduction">-${esc(item.label)} ${fmtScore(item.value)}</span>`
      );
      const chips = [...positive, ...deductions];
      return chips.length ? `<div class="compact-signal-line">${chips.join("")}</div>` : "";
    }

    function renderResultMetadata(hit, rankNumber, scoreValue, sourceMixText, labels, sources) {
      const labelAndSourceChips = [
        ...labels.slice(0, 12).map((label) => `<span class="chip">${esc(label)}</span>`),
        ...sources.map((source) => `<span class="chip">${esc(source)}</span>`)
      ];
      return `
        <div class="detail-section result-metadata-section">
          <div class="detail-title">Result Metadata</div>
          <div class="chips">
            <span class="chip">rank ${fmtNum(rankNumber)}</span>
            <span class="chip mono">${esc(hit.cui)}</span>
            <span class="chip">score ${esc(scoreValue)}</span>
            <span class="chip">${fmtNum(hit.evidence_count || 0)} evidence</span>
            <span class="chip">${esc(matchTypeLabel(hit.match_type || hit.view || ""))}</span>
            ${sourceMixText ? `<span class="chip" title="${esc(sourceMixText)}">${esc(sourceMixText)}</span>` : ""}
          </div>
          ${labelAndSourceChips.length ? `<div class="chips detail-chip-row">${labelAndSourceChips.join("")}</div>` : ""}
        </div>`;
    }

    function renderCompactResultCard(hit, rankNumber) {
      const name = displayNameForHit(hit);
      const semanticTypeLabel = semanticDisplayTypeForHit(hit);
      return `
        <div class="result result-compact">
          <details class="result-details compact-card-details" data-lazy-detail="result" data-doc-id="${esc(hit.doc_id || "")}" data-cui="${esc(hit.cui || "")}" data-rank="${esc(rankNumber || "")}">
            <summary class="compact-result-summary">
              <a class="concept-link compact-result-title" href="${esc(utsConceptUrl(hit.cui))}" target="_blank" rel="noreferrer">
                ${esc(name)}
              </a>
              <span class="result-semantic-type">${esc(semanticTypeLabel)}</span>
              <span class="compact-details-label">Details</span>
            </summary>
            <div class="compact-details-body" data-detail-body>
              <span class="muted">Loading details...</span>
            </div>
          </details>
        </div>`;
    }

    function renderCompactResultDetailsBody(hit, rankNumber) {
      const key = judgmentKey(state.lastQuery, hit.doc_id);
      const grade = state.judgments[key] && state.judgments[key].grade;
      const labels = hit.labels || [];
      const sources = hit.sources || [];
      const scoreValue = Number.isFinite(Number(hit.rank_score || hit.score))
        ? Number(hit.rank_score || hit.score).toFixed(3)
        : "n/a";
      const sourceText = sources.length ? sources.slice(0, 3).join(", ") : "";
      const sourceMixText = sourceMixSummary(hit.source_mix, sources) || sourceText;
      return `
        ${renderResultMetadata(hit, rankNumber, scoreValue, sourceMixText, labels, sources)}
        ${compactSignalSummary(hit)}
        ${renderFeaturedSignalTable(hit)}
        ${renderImageGallery(hit.images || [], true)}
        <div class="detail-section">
          <div class="detail-title">Signal Contribution and Source Mix</div>
          ${renderScoreBreakdown(hit)}
          ${renderSourceMix(hit.source_mix, sources)}
        </div>
        <div class="detail-section">
          <div class="detail-title">Definitions</div>
          ${renderDefinitions(hit.definitions || [])}
        </div>
        <div class="detail-section">
          <div class="detail-title">Code Mappings</div>
          ${renderMappings(hit.mappings || [])}
        </div>
        ${renderRelatedEvidenceSections(hit)}
        <div class="detail-section">
          <div class="detail-title">Evidence</div>
          ${renderEvidenceItems(hit)}
        </div>
        <div class="detail-section">
          <div class="detail-title">Review</div>
          <div class="judgments">
            ${judgmentButton(hit.doc_id, "relevant", "Relevant", grade)}
            ${judgmentButton(hit.doc_id, "partial", "Partial", grade)}
            ${judgmentButton(hit.doc_id, "wrong", "Wrong", grade)}
            <button data-grade="" data-doc="${esc(hit.doc_id)}">Clear</button>
          </div>
        </div>`;
    }

    function detailCacheKey(docId, cui) {
      return `${docId || ""}|${cui || ""}|related:${state.includeRelated ? "1" : "0"}`;
    }

    function mergeDetailHit(baseHit, detailHit) {
      const merged = { ...(detailHit || {}), ...(baseHit || {}) };
      for (const field of [
        "definitions",
        "evidence_items",
        "evidence_related_concepts",
        "external_embedding_neighbors",
        "images",
        "mappings",
        "mrrel_related_concepts",
        "related_concepts",
        "research_relations"
      ]) {
        if (Array.isArray(detailHit?.[field])) merged[field] = detailHit[field];
      }
      if (detailHit?.source_mix) merged.source_mix = detailHit.source_mix;
      if (typeof detailHit?.text === "string") merged.text = detailHit.text;
      return merged;
    }

    async function loadLazyResultDetails(details) {
      if (!details.open || details.dataset.detailLoaded === "1" || details.dataset.detailLoading === "1") return;
      const docId = details.getAttribute("data-doc-id") || "";
      const cui = details.getAttribute("data-cui") || "";
      const rankNumber = Number(details.getAttribute("data-rank") || 0) || 0;
      const body = details.querySelector("[data-detail-body]");
      const baseHit = state.lastResults.find((item) => item.doc_id === docId)
        || state.lastResults.find((item) => item.cui === cui);
      if (!body || !baseHit) return;
      details.dataset.detailLoading = "1";
      body.innerHTML = '<span class="muted">Loading details...</span>';
      try {
        const cacheKey = detailCacheKey(docId, cui);
        let detailHit = state.detailCache.get(cacheKey);
        if (!detailHit) {
          const params = new URLSearchParams();
          if (docId) params.set("doc_id", docId);
          if (cui) params.set("cui", cui);
          params.set("related", state.includeRelated ? "1" : "0");
          const payload = await api(`/api/detail?${params.toString()}`);
          detailHit = payload.hit || {};
          state.detailCache.set(cacheKey, detailHit);
        }
        body.innerHTML = renderCompactResultDetailsBody(mergeDetailHit(baseHit, detailHit), rankNumber);
        details.dataset.detailLoaded = "1";
        bindResultInteractions(body);
      } catch (err) {
        body.innerHTML = `<span class="muted">Details unavailable: ${esc(err?.message || "request failed")}</span>`;
      } finally {
        details.dataset.detailLoading = "";
      }
    }

    function renderResultCard(hit, rankNumber) {
      const key = judgmentKey(state.lastQuery, hit.doc_id);
      const grade = state.judgments[key] && state.judgments[key].grade;
      const labels = hit.labels || [];
      const sources = hit.sources || [];
      const name = displayNameForHit(hit);
      const scoreValue = Number.isFinite(Number(hit.rank_score || hit.score))
        ? Number(hit.rank_score || hit.score).toFixed(3)
        : "n/a";
      const sourceText = sources.length ? sources.slice(0, 3).join(", ") : "n/a";
      const sourceMixText = sourceMixSummary(hit.source_mix, sources) || sourceText;
      const semanticTypeLabel = semanticDisplayTypeForHit(hit);
      return `
        <div class="result">
          <div class="result-visible">
            <a class="concept-link cui-main" href="${esc(utsConceptUrl(hit.cui))}" target="_blank" rel="noreferrer">
              ${esc(name)}
            </a>
            <div class="result-semantic-type">${esc(semanticTypeLabel)}</div>
          </div>
          <details class="result-details">
            <summary>Details</summary>
            ${renderResultMetadata(hit, rankNumber, scoreValue, sourceMixText, labels, sources)}
            ${renderFeaturedSignalTable(hit)}
            <div class="detail-section">
              <div class="detail-title">Signal Contribution and Source Mix</div>
              ${renderScoreBreakdown(hit)}
              ${renderSourceMix(hit.source_mix, sources)}
            </div>
            <div class="detail-section">
              <div class="detail-title">Semantic Types</div>
              <div class="chips">
                ${renderSemanticTypeChips(hit.semantic_types || [])}
              </div>
            </div>
            ${renderImageGallery(hit.images || [])}
            <div class="detail-section">
              <div class="detail-title">Definitions</div>
              ${renderDefinitions(hit.definitions || [])}
            </div>
            <div class="detail-section">
              <div class="detail-title">Code Mappings</div>
              ${renderMappings(hit.mappings || [])}
            </div>
            ${renderRelatedEvidenceSections(hit)}
            <div class="detail-section">
              <div class="detail-title">Evidence</div>
              ${renderEvidenceItems(hit)}
            </div>
            <div class="detail-section">
              <div class="detail-title">Technical</div>
              <div class="chips">
                <span class="chip">score ${Number(hit.score).toFixed(4)}</span>
                <span class="chip">${fmtNum(hit.evidence_count)} evidence</span>
                <span class="chip">${esc(matchTypeLabel(hit.match_type || hit.view || ""))}</span>
                ${hit.matched_input ? `<span class="chip">matched ${esc(hit.matched_input)}</span>` : ""}
                <span class="chip">${esc(hit.doc_id)}</span>
                <span class="chip">${esc(hit.view || "")}</span>
              </div>
            </div>
            <div class="detail-section">
              <div class="detail-title">Review</div>
              <div class="judgments">
                ${judgmentButton(hit.doc_id, "relevant", "Relevant", grade)}
                ${judgmentButton(hit.doc_id, "partial", "Partial", grade)}
                ${judgmentButton(hit.doc_id, "wrong", "Wrong", grade)}
                <button data-grade="" data-doc="${esc(hit.doc_id)}">Clear</button>
              </div>
            </div>
          </details>
        </div>`;
    }

    function renderResults() {
      if (!state.lastResults.length) {
        els.results.innerHTML = '<span class="muted">No results yet.</span>';
        return;
      }
      const resultGroups = mergeRelatedIntoResultBuckets(
        semanticResultBuckets(state.lastResults),
        relatedResultBuckets()
      );
      const hitHtml = resultGroups
        .map((group) => renderResultBucket(group))
        .join("");
      if (!hitHtml) {
        const filterText = (state.selectedSemanticBucketKeys || []).length
          ? "No results matched the selected semantic group filter."
          : "No semantic result groups matched these results.";
        els.results.innerHTML = `<span class="muted">${esc(filterText)}</span>`;
        return;
      }
      const statement = buildStructuredStatement(state.lastQuery || "", state.lastResults);
      const statementHtml = renderStructuredStatementPanel(statement);
      const cohortHtml = renderPatientCohortGroup(buildPatientCohort(state.lastQuery || "", statement));
      els.results.innerHTML = `
        ${statementHtml}
        <div class="results-layout results-layout-full">
          <div class="results-main">${cohortHtml}${hitHtml}</div>
        </div>`;

      bindResultInteractions(els.results);
    }

    function bindResultInteractions(root) {
      root.querySelectorAll("details[data-lazy-detail='result']").forEach((details) => {
        details.addEventListener("toggle", () => {
          loadLazyResultDetails(details);
        });
      });
      root.querySelectorAll(".judgments button").forEach((button) => {
        button.addEventListener("click", () => {
          const docId = button.getAttribute("data-doc");
          const hit = state.lastResults.find((item) => item.doc_id === docId);
          if (hit) setJudgment(hit, button.getAttribute("data-grade"));
        });
      });
      root.querySelectorAll(".related-concept").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          const query = button.getAttribute("data-query") || "";
          if (!query) return;
          els.query.value = query;
          runSearch();
        });
      });
      root.querySelectorAll(".compact-result-summary .concept-link").forEach((link) => {
        link.addEventListener("click", (event) => event.stopPropagation());
      });
    }

    function renderRelatedRail(groupViews, sources, fallbackViews) {
      return "";
    }

    function renderSemanticGroupViews(groupViews) {
      const visibleGroups = (groupViews || []).filter((view) => (view.items || []).length);
      if (!visibleGroups.length) return "";
      return renderSemanticViews(visibleGroups, 12);
    }

    function renderSemanticViewSources(sources) {
      const visibleSources = (sources || []).filter((source) =>
        (source.views || []).some((view) => (view.items || []).length)
      );
      if (!visibleSources.length) return "";
      return visibleSources.slice(0, 10).map((source) => `
        <section class="semantic-source">
          <div class="semantic-source-head">
            <div class="semantic-source-rank">${fmtNum(source.rank || 0)}</div>
            <div>
              <div class="semantic-source-name">${esc(source.source_name || source.source_cui || "Result")}</div>
              <div class="semantic-source-meta">
                <span class="mono">${esc(source.source_cui || "")}</span>
                ${source.source_semantic_group_label ? ` · ${esc(source.source_semantic_group_label)}` : ""}
              </div>
            </div>
          </div>
          ${renderSemanticViews(source.views || [], 4)}
        </section>`).join("");
    }

    function renderSemanticViews(views, itemLimit = 6) {
      const visibleViews = (views || []).filter((view) => (view.items || []).length);
      if (!visibleViews.length) return "";
      return `
        <div class="semantic-view-grid">
          ${visibleViews.map((view) => {
            const items = (view.items || []).slice(0, itemLimit);
            const sourceLine = semanticViewSourceLine(view, items.length);
            return `
              <div class="semantic-view">
                <div class="semantic-view-head">
                  <div>
                    <div class="semantic-view-title">
                      <span>${esc(view.semantic_group_label || view.title || view.category || "Related Concepts")}</span>
                      ${view.semantic_group ? `<span class="semantic-group-code">${esc(view.semantic_group)}</span>` : ""}
                    </div>
                    ${sourceLine ? `<div class="semantic-view-source">${esc(sourceLine)}</div>` : ""}
                  </div>
                  <div class="semantic-view-count">${fmtNum(items.length)} links</div>
                </div>
                <div class="related-items">
                  ${items.map((item) => `
                    <button class="related-concept semantic-concept" data-query="${esc(item.label || item.cui)}" title="${esc(relationLabel(item))}">
                      <span class="semantic-concept-main">
                        <span class="semantic-concept-label">${esc(item.label || item.cui)}</span>
                        <span class="semantic-concept-cui mono">${esc(item.cui)}</span>
                      </span>
                      <span class="semantic-concept-meta">${esc(semanticRelationLabel(item))}</span>
                    </button>`).join("")}
                </div>
              </div>`;
          }).join("")}
        </div>`;
    }

    function semanticViewSourceLine(view, visibleCount) {
      if (view.source_name || view.source_cui) {
        const sourceGroup = view.source_semantic_group_label ? ` · ${view.source_semantic_group_label}` : "";
        return `from ${view.source_name || view.source_cui}${sourceGroup}`;
      }
      const ranks = (view.source_ranks || []).slice(0, 5).map((rank) => `#${rank}`).join(", ");
      if (ranks) {
        const sourceText = view.source_count === 1 ? "result" : "results";
        return `${fmtNum(visibleCount)} links from ${fmtNum(view.source_count || 0)} ${sourceText}: ${ranks}`;
      }
      return "";
    }

    function utsConceptUrl(cui) {
      return `https://uts.nlm.nih.gov/uts/umls/concept/${encodeURIComponent(cui || "")}`;
    }

    function renderSemanticTypeChips(types) {
      if (!types.length) return '<span class="chip">semantic type unavailable</span>';
      return types.map((type) => {
        const label = type.name || type.sty || type.tui || "";
        const tui = type.tui ? ` ${type.tui}` : "";
        return `<span class="chip">${esc(label)}${esc(tui)}</span>`;
      }).join("");
    }

    function matchTypeLabel(value) {
      const map = {
        cui: "direct CUI",
        code: "source code",
        system_code: "source code",
        umls_label: "label match",
        umls_definition: "definition match",
        resolver: "resolver"
      };
      return map[value] || value || "search";
    }

    function renderRelatedConcepts(hit) {
      const related = hit.related_concepts || [];
      if (!related.length) return "";
      const title = hit.related_source === "evidence_vectors"
        ? "Evidence-Related Concepts"
        : (hit.related_source === "external_embeddings" ? "External Embedding Neighbors" : "MRREL Related Concepts");
      return `
        <div class="related-list" style="border-top: 0; padding-top: 0; margin-top: 0;">
          <div class="detail-title">${esc(title)}</div>
          <div class="related-items">
            ${related.slice(0, 8).map((item) => `
              <button class="related-concept" data-query="${esc(item.label || item.cui)}" title="${esc(item.cui)}">
                <span class="mono">${esc(item.cui)}</span>
                <span class="related-label">${esc(item.label || "")}</span>
                <span class="related-meta">${esc(relationLabel(item))}</span>
              </button>`).join("")}
          </div>
        </div>`;
    }

    function renderRelatedEvidenceSections(hit) {
      const content = [
        renderResearchRelations(hit),
        renderExternalEmbeddingNeighbors(hit),
        renderRelatedConcepts(hit),
        renderMrrelConcepts(hit)
      ].filter(Boolean).join("");
      if (!content) return "";
      return `<div class="detail-section">${content}</div>`;
    }

    function renderExternalEmbeddingNeighbors(hit) {
      const neighbors = hit.external_embedding_neighbors || [];
      if (!neighbors.length || hit.related_source === "external_embeddings") return "";
      const grouped = new Map();
      for (const item of neighbors) {
        const key = item.source || "external embedding";
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(item);
      }
      return `
        <div class="related-list" style="border-top: 0; padding-top: 0; margin-top: 0;">
          <div class="detail-title">External Embedding Neighbors</div>
          ${Array.from(grouped.entries()).map(([source, items]) => `
            <div class="small muted" style="margin-top: 6px;">${esc(source)}</div>
            <div class="related-items">
              ${items.slice(0, 6).map((item) => `
                <button class="related-concept" data-query="${esc(item.label || item.cui)}" title="${esc(item.cui)}">
                  <span class="mono">${esc(item.cui)}</span>
                  <span class="related-label">${esc(item.label || "")}</span>
                  <span class="related-meta">${esc(relationLabel(item))}</span>
                </button>`).join("")}
            </div>`).join("")}
        </div>`;
    }

    function renderResearchRelations(hit) {
      const relations = hit.research_relations || [];
      if (!relations.length) return "";
      const grouped = new Map();
      for (const item of relations) {
        const key = item.category_label || item.category || "research links";
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(item);
      }
      return `
        <div class="related-list" style="border-top: 0; padding-top: 0; margin-top: 0;">
          <div class="detail-title">Research Cross-Type Relations</div>
          ${Array.from(grouped.entries()).map(([category, items]) => `
            <div class="small muted" style="margin-top: 6px;">${esc(category)}</div>
            <div class="related-items">
              ${items.slice(0, 6).map((item) => `
                <button class="related-concept" data-query="${esc(item.label || item.cui)}" title="${esc(item.cui)}">
                  <span class="mono">${esc(item.cui)}</span>
                  <span class="related-label">${esc(item.label || "")}</span>
                  <span class="related-meta">${esc(relationLabel(item))}</span>
                </button>`).join("")}
            </div>`).join("")}
        </div>`;
    }

    function renderMrrelConcepts(hit) {
      const related = hit.mrrel_related_concepts || [];
      if (!related.length || hit.related_source === "mrrel") return "";
      return `
        <details class="result-details" style="border-top: 0; margin-top: 8px; padding-top: 0;">
          <summary>MRREL graph support</summary>
          <div class="related-items" style="margin-top: 8px;">
            ${related.slice(0, 8).map((item) => `
              <button class="related-concept" data-query="${esc(item.label || item.cui)}" title="${esc(item.cui)}">
                <span class="mono">${esc(item.cui)}</span>
                <span class="related-label">${esc(item.label || "")}</span>
                <span class="related-meta">${esc(relationLabel(item))}</span>
              </button>`).join("")}
          </div>
        </details>`;
    }

    function renderMappings(mappings) {
      const visibleMappings = dedupeMappings(mappings)
        .filter((row) => String(row.code || "").toUpperCase() !== "NOCODE");
      if (!visibleMappings.length) return '<span class="muted">No external code mappings returned for this hit.</span>';
      return `
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Vocabulary</th>
                <th>Code</th>
                <th>TTY</th>
                <th>Label</th>
              </tr>
            </thead>
            <tbody>
              ${visibleMappings.slice(0, 12).map((row) => `
                <tr>
                  <td>${esc(row.sab || "")}</td>
                  <td class="mono">${esc(row.code || "")}</td>
                  <td>${esc(row.tty || "")}</td>
                  <td>${esc(row.label || "")}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }

    function renderDefinitions(definitions) {
      if (!definitions.length) return '<span class="muted">No MRDEF definitions returned for this hit.</span>';
      return `
        <div class="evidence-list">
          ${definitions.slice(0, 3).map((item) => `
            <div class="evidence-item">
              <div class="evidence-text">${esc(item.definition || "")}</div>
              <div class="evidence-source">
                <span class="source-pill">${esc(item.source || "MRDEF")}</span>
              </div>
            </div>`).join("")}
        </div>`;
    }

    function dedupeMappings(mappings) {
      const ttyPriority = { PT: 0, MH: 1, PN: 2, IN: 3, ET: 4, FN: 5, SY: 6, LLT: 7 };
      const best = new Map();
      for (const row of mappings || []) {
        const key = `${String(row.sab || "").toUpperCase()}|${String(row.code || "").toUpperCase()}`;
        if (!key.trim()) continue;
        const current = best.get(key);
        if (!current || mappingRank(row, ttyPriority) < mappingRank(current, ttyPriority)) {
          best.set(key, row);
        }
      }
      return Array.from(best.values());
    }

    function mappingRank(row, ttyPriority) {
      const ttyRank = ttyPriority[String(row.tty || "").toUpperCase()] ?? 99;
      const prefRank = String(row.ispref || "") === "Y" ? 0 : 1;
      return (ttyRank * 10) + prefRank;
    }

    function relationLabel(item) {
      if (item.relation === "evidence_vector" || item.source === "real-world evidence") {
        const score = Number.isFinite(Number(item.score)) ? ` ${Number(item.score).toFixed(3)}` : "";
        const evidence = item.evidence_count ? ` · ${fmtNum(item.evidence_count)} evidence` : "";
        return `evidence${score}${evidence}`;
      }
      if (item.relation_group) {
        const group = item.relation_group.replaceAll("_", " ");
        const relation = item.rela || item.relation || "related";
        const source = item.source ? ` · ${item.source}` : "";
        const semanticType = item.semantic_type ? ` · ${item.semantic_type}` : "";
        return `${group}: ${relation}${source}${semanticType}`;
      }
      const relation = item.rela || item.relation || "related";
      const source = item.source ? ` · ${item.source}` : "";
      return `${relation}${source}`;
    }

    function semanticRelationLabel(item) {
      const parts = [];
      if (item.source_rank) {
        const sourceName = item.source_name ? ` ${item.source_name}` : "";
        parts.push(`from #${item.source_rank}${sourceName}`);
      }
      if (item.semantic_type) parts.push(item.semantic_type);
      if (item.rela || item.relation) {
        parts.push(String(item.rela || item.relation).replaceAll("_", " "));
      }
      if (item.source) parts.push(item.source);
      return parts.join(" · ");
    }

    function judgmentButton(docId, grade, label, current) {
      const active = current === grade ? " active" : "";
      return `<button class="${active}" data-grade="${grade}" data-doc="${esc(docId)}">${label}</button>`;
    }

    function renderEvidenceItems(hit) {
      const items = hit.evidence_items || [];
      if (!items.length) {
        return `<div class="snippet">${esc(compactEvidence(hit.text || ""))}</div>`;
      }
      return `
        <div class="evidence-list">
          ${items.slice(0, 6).map((item) => `
            <div class="evidence-item">
              <div class="evidence-text">${esc(item.text)}</div>
              <div class="evidence-source">
                ${renderSources(item.sources || [])}
                ${item.weight ? `<span class="source-pill">weight ${esc(item.weight)}</span>` : ""}
              </div>
            </div>`).join("")}
        </div>`;
    }

    function sourceMixSummary(mix, fallbackSources) {
      const items = (mix && mix.items || []).filter((item) => Number(item.sample_refs || 0) > 0);
      if (items.length) {
        return items.slice(0, 2).map((item) => {
          const pct = Number.isFinite(Number(item.sample_pct)) ? ` ${Math.round(Number(item.sample_pct) * 100)}%` : "";
          return `${item.source}${pct}`;
        }).join(", ");
      }
      return (fallbackSources || []).slice(0, 3).join(", ");
    }

    const SIGNAL_COMPONENTS = [
      {
        key: "lexical_component",
        label: "Lexical",
        color: "#2563eb",
        description: "How strongly the query words match the concept name and labels."
      },
      {
        key: "vector_component",
        label: "Vector",
        color: "#0f766e",
        description: "Semantic embedding similarity between the query and the concept document."
      },
      {
        key: "label_fallback_component",
        label: "Label match",
        color: "#64748b",
        description: "A UMLS label-index match rescued or reinforced this concept."
      },
      {
        key: "exact_label_component",
        label: "Exact label",
        color: "#0e7490",
        description: "The normalized query exactly matches one of this concept's UMLS labels."
      },
      {
        key: "exact_primary_name_component",
        label: "Exact primary name",
        color: "#0369a1",
        description: "The normalized query exactly matches the displayed concept name."
      },
      {
        key: "evidence_component",
        label: "Evidence",
        negativeLabel: "Evidence gap",
        color: "#16a34a",
        description: "This concept has visible supporting evidence snippets in the loaded corpus."
      },
      {
        key: "primary_name_component",
        label: "Primary name",
        color: "#0891b2",
        description: "The displayed concept name is specifically covered by the query."
      },
      {
        key: "negated_finding_component",
        label: "Negated finding",
        color: "#7c3aed",
        description: "The query asks about absence or denial, and the concept label reflects that negation."
      },
      {
        key: "semantic_component",
        label: "Semantic type",
        color: "#4338ca",
        description: "The concept's semantic type fits the intent implied by the query."
      },
      {
        key: "evidence_context_component",
        label: "Evidence context",
        color: "#ca8a04",
        description: "Evidence text supports the query context, not just the concept label."
      },
      {
        key: "definition_component",
        label: "Definition",
        color: "#ea580c",
        description: "MRDEF definition text matches important query terms."
      },
      {
        key: "mrrel_component",
        label: "MRREL",
        color: "#7e22ce",
        description: "UMLS MRREL graph support, weighted toward cross-semantic-type links that match query anchors or requested answer roles."
      },
      {
        key: "composite_intent_component",
        label: "Composite intent",
        color: "#be123c",
        description: "Multiple query anchors are satisfied together by this concept."
      },
      {
        key: "first_statement_component",
        label: "First statement",
        color: "#0f766e",
        description: "The concept appears in the first sentence of a multi-sentence paragraph, often the primary assertion."
      },
      {
        key: "local_extension_phrase_component",
        label: "Local exact phrase",
        color: "#9333ea",
        description: "A loaded NEW extension concept exactly matches a multi-token phrase in the query."
      },
      {
        key: "specificity_component",
        label: "Specificity",
        color: "#475569",
        description: "The match covers specific query terms instead of only broad words."
      }
    ];

    const SIGNAL_DEDUCTIONS = [
      {
        key: "generic_penalty",
        label: "Generic concept",
        description: "The matched concept is too broad or generic for the query."
      },
      {
        key: "broad_label_penalty",
        label: "Broad label",
        description: "The displayed concept is a broad class label that misses more specific query anchors."
      },
      {
        key: "relative_specificity_penalty",
        label: "Less specific",
        description: "A more specific returned concept covers the same anchor plus additional query context."
      },
      {
        key: "clinical_context_sense_penalty",
        label: "Context sense",
        description: "The concept uses a query word in the wrong clinical sense for this note context."
      },
      {
        key: "role_mismatch_penalty",
        label: "Role mismatch",
        description: "The concept type does not fit the query role, such as procedure versus condition."
      },
      {
        key: "numeric_specificity_penalty",
        label: "Numeric specificity",
        description: "The query includes a required numeric qualifier, such as type 2, but the concept omits it."
      },
      {
        key: "numeric_context_fragment_penalty",
        label: "Numeric fragment",
        description: "The concept matches a numeric qualifier, such as type 2, but misses the substantive query anchor."
      },
      {
        key: "action_observation_penalty",
        label: "Action mismatch",
        description: "The query asks for an observation/state but the concept is action-like, or vice versa."
      },
      {
        key: "denied_positive_finding_penalty",
        label: "Denied positive finding",
        description: "The query is negated, but the concept represents the positive finding."
      },
      {
        key: "denied_context_mismatch_penalty",
        label: "Denied context mismatch",
        description: "The concept matches words inside a denied phrase but is not itself a negated clinical finding."
      },
      {
        key: "composite_component_penalty",
        label: "Composite component",
        description: "The concept matches only part of a multi-anchor query."
      },
      {
        key: "comparator_arm_penalty",
        label: "Comparator arm",
        description: "The concept appears in a comparator or control arm rather than the primary cohort or assertion."
      },
      {
        key: "sepsis_subtype_penalty",
        label: "Subtype mismatch",
        description: "The concept is a sepsis subtype that does not match the query's specific subtype."
      },
      {
        key: "semantic_fragment_penalty",
        label: "Semantic fragment",
        description: "The concept captures an anatomical or semantic fragment rather than the full query intent."
      },
      {
        key: "generic_fragment_penalty",
        label: "Generic fragment",
        description: "The concept mainly matches a low-specificity query fragment."
      },
      {
        key: "normal_exam_fragment_penalty",
        label: "Exam fragment",
        description: "The concept mainly matches bare exam anatomy, such as heart or lung, instead of the observed exam finding."
      }
    ];

    function scorePart(value) {
      const number = Number(value);
      return Number.isFinite(number) ? number : 0;
    }

    function fmtSignalPct(value) {
      const pct = Number(value) * 100;
      if (!Number.isFinite(pct)) return "0%";
      return `${pct >= 10 ? pct.toFixed(0) : pct.toFixed(1)}%`;
    }

    function signalContributionItems(hit) {
      const breakdown = hit.score_breakdown || {};
      const items = SIGNAL_COMPONENTS.map((component) => ({
        ...component,
        value: scorePart(breakdown[component.key])
      })).filter((item) => item.value > 0);
      const total = items.reduce((sum, item) => sum + item.value, 0);
      return items.map((item) => ({
        ...item,
        share: total ? item.value / total : 0,
        total
      })).sort((a, b) => b.value - a.value);
    }

    function signalDeductionItems(hit) {
      const breakdown = hit.score_breakdown || {};
      const negativeComponents = SIGNAL_COMPONENTS.map((component) => ({
        key: component.key,
        label: component.negativeLabel || `${component.label} deduction`,
        description: component.key === "evidence_component"
          ? "No visible evidence snippets are available for this result in the loaded corpus."
          : `Negative ${component.label.toLowerCase()} signal for this result.`,
        value: Math.abs(Math.min(scorePart(breakdown[component.key]), 0))
      })).filter((item) => item.value > 0);
      const explicitDeductions = SIGNAL_DEDUCTIONS.map((deduction) => ({
        ...deduction,
        value: scorePart(breakdown[deduction.key])
      })).filter((item) => item.value > 0);
      const items = [...negativeComponents, ...explicitDeductions];
      const total = items.reduce((sum, item) => sum + item.value, 0);
      return items.map((item) => ({
        ...item,
        share: total ? item.value / total : 0,
        total
      })).sort((a, b) => b.value - a.value);
    }

    function renderFeaturedSignalTable(hit) {
      const items = signalContributionItems(hit);
      const deductions = signalDeductionItems(hit);
      if (!items.length && !deductions.length) return "";
      return `
        <div class="result-signal-feature">
          <div class="detail-title">Signal Contribution</div>
          <div class="signal-table" aria-label="Signal contribution table">
            <div class="signal-table-row signal-table-head">
              <div class="signal-table-cell">Signal</div>
              <div class="signal-table-cell">Share · Points</div>
              <div class="signal-table-cell">Meaning</div>
            </div>
            ${items.map((item) => `
              <div class="signal-table-row" title="${esc(`${item.label}: ${fmtSignalPct(item.share)} of positive signal (${fmtScore(item.value)} points)`)}">
                <div class="signal-table-cell signal-table-name">
                  <span class="signal-swatch" style="--signal-color: ${item.color};"></span>
                  <span>${esc(item.label)}</span>
                </div>
                <div class="signal-table-cell signal-table-value">${fmtSignalPct(item.share)} · ${fmtScore(item.value)}</div>
                <div class="signal-table-cell signal-table-meaning">${esc(item.description || "Positive rank signal for this result.")}</div>
              </div>`).join("")}
            ${deductions.length ? `
              <div class="signal-table-row signal-table-section">
                <div class="signal-table-cell">Deductions</div>
              </div>
              ${deductions.map((item) => `
                <div class="signal-table-row signal-table-deduction" title="${esc(`${item.label}: ${fmtSignalPct(item.share)} of deductions (${fmtScore(item.value)} points)`)}">
                  <div class="signal-table-cell signal-table-name">
                    <span class="signal-swatch" style="--signal-color: #ea580c;"></span>
                    <span>${esc(item.label)}</span>
                  </div>
                  <div class="signal-table-cell signal-table-value">-${fmtSignalPct(item.share)} · ${fmtScore(item.value)}</div>
                  <div class="signal-table-cell signal-table-meaning">${esc(item.description || "Negative rank signal for this result.")}</div>
                </div>`).join("")}
            ` : ""}
          </div>
        </div>`;
    }

    function renderSignalBreakdown(hit) {
      const items = signalContributionItems(hit);
      const deductions = signalDeductionItems(hit);
      if (!items.length && !deductions.length) {
        return '<div class="muted">No signal components are available.</div>';
      }
      const total = items.length ? items[0].total : 0;
      return `
        ${items.length ? `
          <div class="signal-breakdown">
            <div class="signal-heading">
              <span>Positive Signal</span>
              <span>${fmtScore(total)}</span>
            </div>
            ${items.map((item) => {
              const width = Math.max(1, Math.min(100, item.share * 100));
              const title = `${item.label}: ${fmtSignalPct(item.share)} of positive signal (${fmtScore(item.value)})`;
              return `
                <div class="signal-row" title="${esc(title)}">
                  <div class="signal-label">${esc(item.label)}</div>
                  <div class="signal-meter">
                    <div class="signal-fill" style="width: ${width.toFixed(2)}%; --signal-color: ${item.color};"></div>
                  </div>
                  <div class="signal-value">${fmtSignalPct(item.share)} · ${fmtScore(item.value)}</div>
                </div>`;
            }).join("")}
          </div>` : ""}
        ${deductions.length ? `
          <div class="signal-deductions">
            <div class="chips">
              ${deductions.map((item) => `
                <span class="chip" title="${esc(`${item.label}: ${fmtSignalPct(item.share)} of deductions`)}">
                  -${esc(item.label)} ${fmtSignalPct(item.share)} · ${fmtScore(item.value)}
                </span>`).join("")}
            </div>
          </div>` : ""}
      `;
    }

    function renderScoreBreakdown(hit) {
      const breakdown = hit.score_breakdown || {};
      const scoring = state.lastScoring || {};
      const chips = [
        `retrieval ${breakdown.retrieval_kind || hit.match_type || hit.view || "vector"}`,
        `raw ${fmtScore(breakdown.retrieval_score ?? hit.score)}`,
        `lexical ${fmtScore(breakdown.lexical_component)}`,
        `vector ${fmtScore(breakdown.vector_component)}`,
        `evidence ${fmtScore(breakdown.evidence_component)}`,
        Number(breakdown.exact_label_component || 0) ? `exact label ${fmtScore(breakdown.exact_label_component)}` : "",
        Number(breakdown.exact_primary_name_component || 0) ? `exact primary ${fmtScore(breakdown.exact_primary_name_component)}` : "",
        Number(breakdown.definition_component || 0) ? `definition ${fmtScore(breakdown.definition_component)}` : "",
        Number(breakdown.primary_name_component || 0) ? `primary name ${fmtScore(breakdown.primary_name_component)}` : "",
        Number(breakdown.negated_finding_component || 0) ? `negated finding ${fmtScore(breakdown.negated_finding_component)}` : "",
        Number(breakdown.semantic_component || 0) ? `semantic ${fmtScore(breakdown.semantic_component)}` : "",
        Number(breakdown.generic_penalty || 0) ? `generic penalty ${fmtScore(breakdown.generic_penalty)}` : ""
      ].filter(Boolean);
      const scoringText = [scoring.retrieval, scoring.ranker, scoring.source_role].filter(Boolean).join(" | ");
      return `
        ${renderSignalBreakdown(hit)}
        <div class="chips">
          ${chips.map((chip) => `<span class="chip">${chip}</span>`).join("")}
        </div>
        ${scoringText ? `<div class="muted">${esc(scoringText)}</div>` : ""}
      `;
    }

    function renderSourceMix(mix, fallbackSources) {
      const items = mix && mix.items || [];
      if (!items.length && !(fallbackSources || []).length) {
        return '<span class="muted">No source mix is available.</span>';
      }
      const total = Number(mix && mix.sample_refs || 0);
      const sourceItems = items.length
        ? items
        : (fallbackSources || []).map((source) => ({ source, sample_refs: 0, sample_pct: null }));
      return `
        <div class="chips">
          ${sourceItems.slice(0, 8).map((item) => {
            const count = Number(item.sample_refs || 0);
            const pct = Number.isFinite(Number(item.sample_pct)) ? ` · ${Math.round(Number(item.sample_pct) * 100)}%` : "";
            const countText = total ? `${fmtNum(count)} refs${pct}` : "present";
            return `<span class="chip">${esc(item.source)}: ${countText}</span>`;
          }).join("")}
        </div>
        <div class="muted">${esc((mix && mix.note) || "Source mix is based on the visible evidence sample.")}</div>
      `;
    }

    function fmtScore(value) {
      return Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "n/a";
    }

    function renderSources(sources) {
      if (!sources.length) return '<span class="source-pill">source not found in loaded evidence shards</span>';
      return sources.map((source) => {
        const label = source.label || source.corpus_doc_id || source.source || "source";
        const details = [
          source.matched_label ? `matched ${source.matched_label}` : "",
          source.source_label ? source.source_label : ""
        ].filter(Boolean).join(" | ");
        const text = details ? `${label} | ${details}` : label;
        if (source.url) {
          return `<a class="source-link" href="${esc(source.url)}" target="_blank" rel="noreferrer">${esc(text)}</a>`;
        }
        return `<span class="source-pill">${esc(text)}</span>`;
      }).join("");
    }

    function compactEvidence(text) {
      if (!text) return "No evidence text is available for this result.";
      const lines = String(text).split(/\n/);
      const evidenceIndex = lines.findIndex(
        (line) => line.startsWith("Real-world evidence:") || line.startsWith("Open literature evidence:")
      );
      if (evidenceIndex >= 0) {
        return lines.slice(0, 12).join("\n") + "\n" + lines.slice(evidenceIndex, evidenceIndex + 5).join("\n");
      }
      return String(text).slice(0, 1400);
    }

    function gradeWeight(grade) {
      if (grade === "relevant") return 1;
      if (grade === "partial") return 0.5;
      return 0;
    }

    function currentQueryMetrics() {
      if (!state.lastResults.length) return { p5: "n/a", mrr: "n/a" };
      let score5 = 0;
      let judged5 = 0;
      let reciprocal = 0;
      state.lastResults.forEach((hit, idx) => {
        const grade = state.judgments[judgmentKey(state.lastQuery, hit.doc_id)]?.grade;
        const weight = gradeWeight(grade);
        if (idx < 5 && grade) {
          score5 += weight;
          judged5 += 1;
        }
        if (!reciprocal && weight > 0) reciprocal = 1 / (idx + 1);
      });
      return {
        p5: judged5 ? fmtPct(score5 / 5) : "unjudged",
        mrr: reciprocal ? reciprocal.toFixed(3) : "unjudged"
      };
    }

    function renderMetrics() {
      const judged = Object.values(state.judgments);
      const relevant = judged.filter((row) => row.grade === "relevant").length;
      const partial = judged.filter((row) => row.grade === "partial").length;
      const wrong = judged.filter((row) => row.grade === "wrong").length;
      const current = currentQueryMetrics();
      const provenanceMode = state.status?.provenance_mode ? ` via ${state.status.provenance_mode}` : "";
      const relatedLinks = state.status?.related_concept_links || 0;
      const researchLinks = state.status?.research_relation_links || 0;
      const definitionRows = state.status?.definition_rows || 0;
      const codeMappings = state.status?.code_mappings || 0;
      els.metrics.innerHTML = [
        metric("Vectors", fmtNum(state.status?.records || 0), `${fmtNum(state.status?.docs || 0)} docs, ${fmtNum(state.status?.evidence_sources || 0)} source refs${provenanceMode}`),
        metric("Backend", state.status?.search_backend || "n/a", state.status?.elastic_index || "local vector scan"),
        metric("Model", state.status?.embedding_provider || "n/a", state.status?.embedding_model || "n/a"),
        metric("Resolver", fmtNum(codeMappings), codeMappings ? "CUI/code mappings loaded" : "No code index loaded"),
        metric("Definitions", fmtNum(definitionRows), definitionRows ? `${fmtNum(state.status?.definition_cuis || 0)} CUIs with MRDEF text` : "No MRDEF index loaded"),
        metric("Evidence related", fmtNum(state.status?.records || 0), "Nearest CUI/view vectors on result concepts"),
        metric("MRREL support", fmtNum(relatedLinks), relatedLinks ? `${fmtNum(state.status?.related_concept_sources || 0)} CUIs with links` : "No relation index loaded"),
        metric("Research links", fmtNum(researchLinks), researchLinks ? `${fmtNum(state.status?.research_relation_sources || 0)} CUIs with cross-type links` : "No research relation index loaded"),
        metric("Judged results", fmtNum(judged.length), `${relevant} relevant, ${partial} partial, ${wrong} wrong`),
        metric("Current P@5", current.p5, "Relevant=1, partial=0.5")
      ].join("");
    }

    function metric(label, value, detail) {
      return `
        <div class="metric">
          <div class="label">${esc(label)}</div>
          <div class="value">${esc(value)}</div>
          <div class="muted small">${esc(detail)}</div>
        </div>`;
    }

    function isExpectedCui(value) {
      return /^(?:C\d{7}|NEW\d{7})$/i.test(String(value || "").trim());
    }

    function normalizeExpectedCuis(value) {
      return String(value || "")
        .split(/[|;,]/)
        .map((part) => part.trim().toUpperCase())
        .filter((part) => isExpectedCui(part));
    }

    function parseQuerySetLine(line) {
      const value = String(line || "").trim();
      if (!value) return null;
      const tabIndex = value.indexOf("\t");
      if (tabIndex >= 0) {
        return {
          query: value.slice(0, tabIndex).trim(),
          expectedCuis: normalizeExpectedCuis(value.slice(tabIndex + 1))
        };
      }
      const expectedMatch = value.match(/,\s*((?:C\d{7}|NEW\d{7})(?:\s*[,|;]\s*(?:C\d{7}|NEW\d{7}))*)\s*$/i);
      if (expectedMatch) {
        return {
          query: value.slice(0, expectedMatch.index).trim(),
          expectedCuis: normalizeExpectedCuis(expectedMatch[1])
        };
      }
      return { query: value, expectedCuis: [] };
    }

    function parseQuerySet() {
      return els.querySet.value
        .split(/\r?\n/)
        .map(parseQuerySetLine)
        .filter((row) => row && row.query)
        .map((row) => {
          const expected = row.expectedCuis.join("|");
          return {
            query: row.query,
            expected,
            expectedCuis: row.expectedCuis
          };
        });
    }

    async function runQuerySet() {
      const rows = parseQuerySet();
      const topK = Math.max(1, Math.min(100, Number(els.topK.value) || 10));
      if (!rows.length) {
        setQuerySetFeedback("Add one query per line before running the query set.", "error");
        return;
      }
      state.setRows = [];
      els.runSetBtn.disabled = true;
      if (els.setResults) els.setResults.setAttribute("aria-busy", "true");
      setQuerySetFeedback(`Running 0 of ${fmtNum(rows.length)} queries.`);
      renderSetResults();
      try {
        for (let i = 0; i < rows.length; i += 1) {
          const row = rows[i];
          setBrandStatus();
          setQuerySetFeedback(`Running ${fmtNum(i + 1)} of ${fmtNum(rows.length)} queries.`);
          const payload = await api(
            `/api/search?q=${encodeURIComponent(row.query)}&k=${topK}&related=0${semanticBucketFilterQueryParam()}`
          );
          const hits = payload.hits || [];
          let expectedRank = "";
          let expectedFound = "";
          let missingExpected = "";
          if (row.expectedCuis.length) {
            const ranksByCui = new Map();
            hits.forEach((hit, index) => {
              const cui = String(hit.cui || "").toUpperCase();
              if (cui && !ranksByCui.has(cui)) ranksByCui.set(cui, index + 1);
            });
            const foundRanks = row.expectedCuis
              .map((cui) => ranksByCui.get(cui))
              .filter((rank) => Number.isFinite(rank));
            const missingCuis = row.expectedCuis.filter((cui) => !ranksByCui.has(cui));
            expectedRank = foundRanks.length ? Math.min(...foundRanks) : `>${topK}`;
            expectedFound = `${fmtNum(foundRanks.length)}/${fmtNum(row.expectedCuis.length)}`;
            missingExpected = missingCuis.join("|");
          }
          const topScore = Number(hits[0]?.rank_score ?? hits[0]?.score ?? 0);
          state.setRows.push({
            query: row.query,
            expected: row.expected,
            expectedRank,
            expectedFound,
            missingExpected,
            topCui: hits[0]?.cui || "",
            topLabel: hits[0]?.labels?.[0] || "",
            topScore
          });
          renderSetResults();
        }
        setQuerySetFeedback(`Finished ${fmtNum(rows.length)} ${rows.length === 1 ? "query" : "queries"}.`);
      } catch (err) {
        const completed = state.setRows.length;
        setQuerySetFeedback(
          `Query set stopped after ${fmtNum(completed)} of ${fmtNum(rows.length)} queries: ${err?.message || "request failed"}`,
          "error"
        );
      } finally {
        els.runSetBtn.disabled = false;
        if (els.setResults) els.setResults.setAttribute("aria-busy", "false");
        setBrandStatus();
        renderSetResults();
      }
    }

    function renderSetResults() {
      if (!state.setRows.length) {
        els.setResults.innerHTML = '<table><tbody><tr><td class="muted">No query set has been run.</td></tr></tbody></table>';
        return;
      }
      els.setResults.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Query</th>
              <th>Expected CUI</th>
              <th>Found</th>
              <th>Expected rank</th>
              <th>Missing expected</th>
              <th>Top result</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            ${state.setRows.map((row) => `
              <tr>
                <td>${esc(row.query)}</td>
                <td class="mono">${esc(row.expected || "")}</td>
                <td>${esc(row.expectedFound || "")}</td>
                <td>${esc(row.expectedRank || "")}</td>
                <td class="mono">${esc(row.missingExpected || "")}</td>
                <td><span class="mono">${esc(row.topCui)}</span> ${esc(row.topLabel)}</td>
                <td class="mono">${row.topScore ? Number(row.topScore).toFixed(4) : ""}</td>
              </tr>`).join("")}
          </tbody>
        </table>`;
    }

    function exportJudgments() {
      const rows = [["query", "doc_id", "cui", "view", "score", "grade", "labels"]];
      for (const row of Object.values(state.judgments)) {
        rows.push([
          row.query,
          row.doc_id,
          row.cui,
          row.view,
          row.score,
          row.grade,
          (row.labels || []).join("; ")
        ]);
      }
      const csv = rows.map((row) => row.map(csvCell).join(",")).join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "search_quality_judgments.csv";
      a.click();
      URL.revokeObjectURL(url);
    }

    function csvCell(value) {
      return `"${String(value ?? "").replaceAll('"', '""')}"`;
    }

    els.searchBtn.addEventListener("click", runSearch);
    els.query.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runSearch();
    });
    if (els.clinicalSuggestionSelect) {
      els.clinicalSuggestionSelect.addEventListener("change", () => {
        runSelectedDropdownQuery(els.clinicalSuggestionSelect, clinicalNoteSuggestions);
      });
    }
    if (els.paragraphTestSelect) {
      els.paragraphTestSelect.addEventListener("change", () => {
        runSelectedDropdownQuery(els.paragraphTestSelect, paragraphTests);
      });
    }
    if (els.semanticGroupFilter) {
      els.semanticGroupFilter.addEventListener("change", () => {
        state.selectedSemanticBucketKeys = selectedSemanticBucketKeys();
        if (state.lastQuery) runSearch();
      });
    }
    els.runSetBtn.addEventListener("click", runQuerySet);
    els.saveJudgmentsBtn.addEventListener("click", () => {
      persistJudgmentsToServer().catch((err) => {
        setBrandStatus();
      });
    });
    els.clearJudgmentsBtn.addEventListener("click", () => {
      state.judgments = {};
      saveJudgments();
      renderResults();
      renderMetrics();
      persistJudgmentsToServer().catch((err) => {
        setBrandStatus();
      });
    });
    els.exportBtn.addEventListener("click", exportJudgments);

    loadClinicalNoteSuggestions().then(renderClinicalNoteSuggestions);
    loadParagraphTests().then(renderParagraphTests);
    semanticResultBucketsReady = loadSemanticResultBuckets().then(renderSemanticGroupFilter);
    semanticExpansionProfilesReady = loadSemanticExpansionProfiles();
    renderMetrics();
    loadStatus().then(loadServerJudgments);
