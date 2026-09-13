#!/usr/bin/env bash
# Deploy the demo as an AWS Lambda container behind a Function URL (ADR-022).
#
#   deploy/aws/lambda.sh            # build, push to ECR, deploy, print the URL
#   deploy/aws/lambda.sh --teardown # delete the function, the URL and the repo
#
# Lambda because the alternatives are shut: App Runner answers
# SubscriptionRequiredException on this account, Lightsail container services
# are quota-blocked at zero, and Fly and Hugging Face both want payment before
# they create anything. Lambda also happens to be the cheapest and the only one
# whose free tier is perpetual rather than promotional.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
NAME="${LAMBDA_NAME:-receipts-demo}"
MEMORY="${LAMBDA_MEMORY:-1024}"   # measured: 161MB under load. 1GB buys CPU, which Lambda scales with memory.
TIMEOUT="${LAMBDA_TIMEOUT:-60}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING="${REPO_ROOT}/.make/aws-image"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

teardown() {
  log "Tearing down ${NAME} in ${REGION}"
  aws lambda delete-function-url-config --function-name "${NAME}" --region "${REGION}" 2>/dev/null || true
  aws lambda delete-function --function-name "${NAME}" --region "${REGION}" 2>/dev/null || true
  aws ecr delete-repository --repository-name "${NAME}" --force --region "${REGION}" 2>/dev/null || true
  aws iam delete-role-policy --role-name "${NAME}-role" --policy-name basic 2>/dev/null || true
  aws iam detach-role-policy --role-name "${NAME}-role" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
  aws iam delete-role --role-name "${NAME}-role" 2>/dev/null || true
  echo "deleted. Nothing is running and nothing is stored."
  exit 0
}
[[ "${1:-}" == "--teardown" ]] && teardown

[[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]] && {
  echo "the tree is dirty; commit first so the URL identifies a commit" >&2; exit 1; }
COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
TAG="${COMMIT:0:12}"

# --------------------------------------------------------------------------- #
# 1. Stage from the commit, exactly as deploy.sh does.
# --------------------------------------------------------------------------- #
log "Staging at ${TAG}"
rm -rf "${STAGING}"; mkdir -p "${STAGING}"
cd "${REPO_ROOT}"
cp deploy/spaces/Dockerfile "${STAGING}/Dockerfile"
cp pyproject.toml requirements.lock "${STAGING}/"
for path in src config semantic prompts scripts web; do
  git archive "${COMMIT}" "${path}" | tar -x -C "${STAGING}"
done
mkdir -p "${STAGING}/eval"
git archive "${COMMIT}" eval/recordings eval/questions/dev.jsonl | tar -x -C "${STAGING}"
[[ -f data/kestrel.duckdb ]] || { echo "data/kestrel.duckdb missing; run make data" >&2; exit 1; }
cp data/kestrel.duckdb "${STAGING}/kestrel.duckdb"
shasum -a 256 data/kestrel.duckdb | awk '{print $1}' > "${STAGING}/data_version.txt"
if find "${STAGING}" -path '*sealed*' -o -name 'holdout*' -o -name '.env' | grep -q .; then
  echo "refusing to deploy: sealed or holdout material reached the image context" >&2; exit 1
fi

log "Building linux/amd64 (pip layer caches; only changed source rebuilds)"
docker buildx build --platform linux/amd64 -t "${NAME}:${TAG}" --load "${STAGING}"

# --------------------------------------------------------------------------- #
# 2. ECR, and the Lambda layer pushed straight to it.
# --------------------------------------------------------------------------- #
log "Pushing to ECR"
aws ecr describe-repositories --repository-names "${NAME}" --region "${REGION}" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "${NAME}" --region "${REGION}" >/dev/null
aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${ECR}"

# `--provenance=false --sbom=false` and `oci-mediatypes=false` are not tuning.
# buildx defaults to OCI manifests and adds an attestation manifest, which turns
# the push into a manifest LIST -- and Lambda answers
#
#   InvalidParameterValueException: The image manifest, config or layer media
#   type for the source image ... is not supported
#
# Lambda takes Docker v2 schema 2 and nothing else. Built and pushed in one
# step so the thing that lands in ECR is the thing that was built.
docker buildx build --platform linux/amd64 \
  --provenance=false --sbom=false \
  --build-arg "BASE=${NAME}:${TAG}" \
  -f deploy/aws/Dockerfile.lambda \
  --output "type=image,name=${ECR}/${NAME}:${TAG},push=true,oci-mediatypes=false" \
  deploy/aws

# --------------------------------------------------------------------------- #
# 3. Role, function, URL.
# --------------------------------------------------------------------------- #
if ! aws iam get-role --role-name "${NAME}-role" >/dev/null 2>&1; then
  log "Creating the execution role"
  aws iam create-role --role-name "${NAME}-role" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "${NAME}-role" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "waiting for IAM to propagate"
  sleep 15
fi
ROLE_ARN="$(aws iam get-role --role-name "${NAME}-role" --query Role.Arn --output text)"

if aws lambda get-function --function-name "${NAME}" --region "${REGION}" >/dev/null 2>&1; then
  log "Updating the function"
  aws lambda update-function-code --function-name "${NAME}" \
    --image-uri "${ECR}/${NAME}:${TAG}" --region "${REGION}" >/dev/null
else
  log "Creating the function"
  aws lambda create-function --function-name "${NAME}" \
    --package-type Image --code "ImageUri=${ECR}/${NAME}:${TAG}" \
    --role "${ROLE_ARN}" --memory-size "${MEMORY}" --timeout "${TIMEOUT}" \
    --region "${REGION}" >/dev/null
fi

echo "waiting for the function to become Active"
aws lambda wait function-active-v2 --function-name "${NAME}" --region "${REGION}" || true
aws lambda wait function-updated-v2 --function-name "${NAME}" --region "${REGION}" || true

log "Function URL"
if ! aws lambda get-function-url-config --function-name "${NAME}" --region "${REGION}" >/dev/null 2>&1; then
  aws lambda create-function-url-config --function-name "${NAME}" \
    --auth-type NONE --invoke-mode RESPONSE_STREAM --region "${REGION}" >/dev/null
  aws lambda add-permission --function-name "${NAME}" --statement-id public \
    --action lambda:InvokeFunctionUrl --principal '*' \
    --function-url-auth-type NONE --region "${REGION}" >/dev/null
fi
URL="$(aws lambda get-function-url-config --function-name "${NAME}" --region "${REGION}" \
  --query FunctionUrl --output text)"

log "Live"
echo "${URL}"
echo "${URL}?role=rm_tamil_nadu   <- try as the Chennai manager"
echo
echo "Tear it down with:  deploy/aws/lambda.sh --teardown"
