# Receipts — the Hugging Face Spaces demo (ADR-022).
#
# The Space repository IS the deployed snapshot: `push.py` uploads the source
# subset the API needs, the built-from-source front end, and the warehouse, and
# the Space's own commit records exactly what is running. An earlier version
# cloned the GitHub repo at a pinned SHA during the build; it needed the network
# twice inside Docker and failed on TLS resets after four to eight minutes. A
# build that depends on a network round trip is a build that fails on somebody
# else's bad afternoon.
#
# Replay mode, always: no model call, no API key, no per-question cost.

# --------------------------------------------------------------------------- #
# Stage 1: the front end, from the source in this repository.
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
    RECEIPTS_LLM_MODE=replay \
    DEMO_MODE=true \
    HOME=/home/receipts

# Spaces runs as uid 1000 and gives the container an ephemeral filesystem, so
# the app lives under $HOME where it can write its audit log. That log does not
# survive a restart, which is stated in LIMITATIONS rather than left to be
# discovered.
RUN useradd --create-home --uid 1000 receipts
WORKDIR /home/receipts/app

COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY src/ ./src/
COPY config/ ./config/
COPY semantic/ ./semantic/
COPY prompts/ ./prompts/
COPY scripts/ ./scripts/
COPY eval/ ./eval/
RUN pip install --no-cache-dir --no-deps -e .

COPY --from=web /web/dist ./web/dist

# The warehouse, checked rather than trusted: a demo answering from a different
# world than the one the receipts describe is the exact failure this project is
# about.
COPY kestrel.duckdb ./data/kestrel.duckdb
COPY data_version.txt ./data/data_version.txt
RUN python - <<'PY'
import hashlib, pathlib
db = pathlib.Path("data/kestrel.duckdb")
expected = pathlib.Path("data/data_version.txt").read_text().split()[0].strip()
digest = hashlib.sha256(db.read_bytes()).hexdigest()
print(f"warehouse sha256 {digest}")
if digest != expected:
    raise SystemExit(f"warehouse hash {digest} != recorded {expected}")
print("warehouse matches the hash recorded when it was uploaded")
PY

RUN chown -R receipts:receipts /home/receipts
USER receipts

# Spaces routes to 7860 by default; `app_port` in README.md keeps the two honest.
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "--factory", "receipts.api.app:create_app", \
     "--host", "0.0.0.0", "--port", "7860"]
