FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
RUN mkdir -p /workspace/scripts /workspace/src /workspace/build /workspace/config \
    /workspace/docs /workspace/web/search_quality /workspace/docker/umls

COPY docker/umls/requirements.txt /tmp/umls-requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/umls-requirements.txt

COPY src /workspace/src
COPY scripts/search_quality_server.py /workspace/scripts/search_quality_server.py
COPY scripts/start_search_quality_server.sh /workspace/scripts/start_search_quality_server.sh
COPY scripts/public_search_preflight.py /workspace/scripts/public_search_preflight.py
COPY scripts/ensure_public_search_payload.py /workspace/scripts/ensure_public_search_payload.py
COPY scripts/ensure_sapbert_cache.py /workspace/scripts/ensure_sapbert_cache.py
COPY scripts/scaling_status.py /workspace/scripts/scaling_status.py
COPY scripts/runtime_elastic.py /workspace/scripts/runtime_elastic.py
COPY config/search_quality_semantic_buckets.json /workspace/config/search_quality_semantic_buckets.json
COPY config/active_label_supplement.tsv /workspace/config/active_label_supplement.tsv
COPY config/display_name_overrides.tsv /workspace/config/display_name_overrides.tsv
COPY web/search_quality_product.html /workspace/web/search_quality_product.html
COPY web/search_quality/app.js /workspace/web/search_quality/app.js
COPY web/search_quality/server.css /workspace/web/search_quality/server.css
COPY web/search_quality/uts-banner.jpg /workspace/web/search_quality/uts-banner.jpg
COPY web/search_quality/nih-nlm-logo.png /workspace/web/search_quality/nih-nlm-logo.png
COPY web/search_quality/suggestions.json /workspace/web/search_quality/suggestions.json
COPY web/search_quality/paragraphs.json /workspace/web/search_quality/paragraphs.json
COPY web/search_quality/real_short_queries.json /workspace/web/search_quality/real_short_queries.json
COPY web/search_quality/expansion_profiles.json /workspace/web/search_quality/expansion_profiles.json
COPY docker/umls /workspace/docker/umls

EXPOSE 8766

CMD ["sh", "-lc", "scripts/start_search_quality_server.sh --host 0.0.0.0"]
