# The one deployable: the API, with the built front end inside it (SDD §22).
#
# Two stages, and the reason is the claim in the README rather than image size:
# the front end is BUILT here, from source, so "npm run build outputs static
# files that FastAPI serves at /" is something the image proves rather than
# something a committed dist/ directory asserts.
#
# What is NOT in this image: the warehouse (data/ is generated, ~3.5 min, and
# belongs in a volume) and the model recordings are, because replay is how the
# demo answers without a network (D9, ADR-005).

# --------------------------------------------------------------------------- #
# Stage 1: the front end.
# --------------------------------------------------------------------------- #
FROM node:22-alpine AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --------------------------------------------------------------------------- #
# Stage 2: the API, serving it.
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RECEIPTS_LLM_MODE=replay

WORKDIR /app

COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY src/ ./src/
COPY config/ ./config/
COPY semantic/ ./semantic/
COPY prompts/ ./prompts/
COPY scripts/ ./scripts/
COPY eval/recordings/ ./eval/recordings/
RUN pip install --no-cache-dir --no-deps -e .

# The built SPA, at the path create_app() mounts from.
COPY --from=web /web/dist ./web/dist

# Not root. The DB role is read-only and so is this one; two independent layers
# saying the same thing is the point (D8).
RUN useradd --create-home --uid 10001 receipts && chown -R receipts /app
USER receipts

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

CMD ["python", "-m", "uvicorn", "--factory", "receipts.api.app:create_app", \
     "--host", "0.0.0.0", "--port", "8000"]
