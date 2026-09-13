#!/usr/bin/env bash
# Deploy the demo to AWS Lightsail Containers (ADR-022).
#
#   deploy/aws/deploy.sh            # build, push, deploy, print the URL
#   deploy/aws/deploy.sh --teardown # delete the service and stop the meter
#
# Why Lightsail and not the others, on this account: App Runner answers
# SubscriptionRequiredException, Fly and Hugging Face both now want payment
# before they will create anything, and EC2 would mean managing TLS by hand.
# Lightsail hands back an HTTPS URL for a container and deletes in one call.
#
# The image is the SELF-CONTAINED one from deploy/spaces/Dockerfile: source at
# the pinned commit, the front end built from that source, and the warehouse
# baked in with its SHA-256 checked at build time. Nothing is fetched at run
# time and no model is ever called -- RECEIPTS_LLM_MODE=replay.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
SERVICE="${LIGHTSAIL_SERVICE:-receipts-demo}"
POWER="${LIGHTSAIL_POWER:-micro}"   # micro = 1GB / 0.5 vCPU, $10/mo, ~$0.33/day
SCALE=1
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING="${REPO_ROOT}/.make/aws-image"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

teardown() {
  log "Deleting ${SERVICE} in ${REGION}"
  aws lightsail delete-container-service --service-name "${SERVICE}" --region "${REGION}"
  echo "deleted. The meter has stopped."
  exit 0
}

[[ "${1:-}" == "--teardown" ]] && teardown

# --------------------------------------------------------------------------- #
# 1. Stage the image context from the CURRENT COMMIT.
# --------------------------------------------------------------------------- #
if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "the tree is dirty; commit before deploying so the URL identifies a commit" >&2
  exit 1
fi
COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
log "Staging the image context at ${COMMIT:0:12}"

rm -rf "${STAGING}"; mkdir -p "${STAGING}"
cd "${REPO_ROOT}"
cp deploy/spaces/Dockerfile "${STAGING}/Dockerfile"
cp pyproject.toml requirements.lock "${STAGING}/"
for path in src config semantic prompts scripts web; do
  git archive "${COMMIT}" "${path}" | tar -x -C "${STAGING}"
done
mkdir -p "${STAGING}/eval"
git archive "${COMMIT}" eval/recordings eval/questions/dev.jsonl | tar -x -C "${STAGING}"

# The warehouse is generated and never committed, so it comes from the working
# tree -- and its hash travels with it so the build refuses a mismatch.
[[ -f data/kestrel.duckdb ]] || { echo "data/kestrel.duckdb missing; run make data" >&2; exit 1; }
cp data/kestrel.duckdb "${STAGING}/kestrel.duckdb"
shasum -a 256 data/kestrel.duckdb | awk '{print $1}' > "${STAGING}/data_version.txt"
echo "warehouse sha256 $(cat "${STAGING}/data_version.txt")"

# Nothing sealed, ever (HANDOFF §4.8).
if find "${STAGING}" -path '*sealed*' -o -name 'holdout*' -o -name '.env' | grep -q .; then
  echo "refusing to deploy: sealed or holdout material reached the image context" >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# 2. Build for linux/amd64. Lightsail is x86; this machine is arm64.
# --------------------------------------------------------------------------- #
log "Building linux/amd64 image"
docker buildx build --platform linux/amd64 -t "${SERVICE}:${COMMIT:0:12}" --load "${STAGING}"

# --------------------------------------------------------------------------- #
# 3. Create the service if it is not there, then push and deploy.
# --------------------------------------------------------------------------- #
if ! aws lightsail get-container-services --service-name "${SERVICE}" --region "${REGION}" >/dev/null 2>&1; then
  log "Creating the container service (${POWER}, scale ${SCALE})"
  aws lightsail create-container-service \
    --service-name "${SERVICE}" --power "${POWER}" --scale "${SCALE}" --region "${REGION}" >/dev/null
  echo "waiting for it to become READY"
  for _ in $(seq 1 60); do
    state=$(aws lightsail get-container-services --service-name "${SERVICE}" --region "${REGION}" \
      --query 'containerServices[0].state' --output text)
    echo "  state: ${state}"
    [[ "${state}" == "READY" ]] && break
    sleep 10
  done
fi

log "Pushing the image"
PUSH_OUT=$(aws lightsail push-container-image \
  --service-name "${SERVICE}" --label app --image "${SERVICE}:${COMMIT:0:12}" --region "${REGION}" 2>&1)
echo "${PUSH_OUT}"
IMAGE_REF=$(echo "${PUSH_OUT}" | grep -oE ':receipts-demo\.app\.[0-9]+' | tail -1)
[[ -n "${IMAGE_REF}" ]] || { echo "could not read the pushed image reference" >&2; exit 1; }
echo "pushed as ${IMAGE_REF}"

log "Deploying"
cat > "${STAGING}/containers.json" <<JSON
{
  "app": {
    "image": "${IMAGE_REF}",
    "environment": {
      "RECEIPTS_LLM_MODE": "replay",
      "DEMO_MODE": "true",
      "RECEIPTS_COMMIT": "${COMMIT}"
    },
    "ports": { "7860": "HTTP" }
  }
}
JSON
cat > "${STAGING}/endpoint.json" <<JSON
{
  "containerName": "app",
  "containerPort": 7860,
  "healthCheck": {
    "path": "/healthz",
    "intervalSeconds": 10,
    "timeoutSeconds": 5,
    "healthyThreshold": 2,
    "unhealthyThreshold": 5,
    "successCodes": "200"
  }
}
JSON
aws lightsail create-container-service-deployment \
  --service-name "${SERVICE}" --region "${REGION}" \
  --containers "file://${STAGING}/containers.json" \
  --public-endpoint "file://${STAGING}/endpoint.json" >/dev/null

log "Waiting for the deployment"
for _ in $(seq 1 90); do
  state=$(aws lightsail get-container-services --service-name "${SERVICE}" --region "${REGION}" \
    --query 'containerServices[0].currentDeployment.state' --output text 2>/dev/null || echo PENDING)
  echo "  deployment: ${state}"
  [[ "${state}" == "ACTIVE" ]] && break
  [[ "${state}" == "FAILED" ]] && { echo "deployment failed" >&2; exit 1; }
  sleep 10
done

URL=$(aws lightsail get-container-services --service-name "${SERVICE}" --region "${REGION}" \
  --query 'containerServices[0].url' --output text)
log "Live"
echo "${URL}"
echo "${URL}?role=rm_tamil_nadu   <- try as the Chennai manager"
echo
echo "Tear it down with:  deploy/aws/deploy.sh --teardown"
