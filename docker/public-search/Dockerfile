FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt /tmp/public-search-requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/public-search-requirements.txt

EXPOSE 8766

CMD ["sh", "-lc", "scripts/start_search_quality_server.sh --host 0.0.0.0"]
