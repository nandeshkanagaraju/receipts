#!/usr/bin/env bash
# Deploy the demo on a single EC2 instance (ADR-022).
#
#   deploy/aws/ec2.sh            # launch, run the container, print the URL
#   deploy/aws/ec2.sh --teardown # terminate and delete everything it made
#
# The fifth host attempted, and the one that worked. In order: Fly wanted a
# card; Hugging Face now wants PRO for Docker Spaces; App Runner answers
# SubscriptionRequiredException on this account; Lightsail container services
# are quota-blocked at zero; Lambda refused the image with
# `Runtime.InvalidEntrypoint: ProcessPermissionDenied` through four fixes --
# root, the extension's file mode, an absolute entrypoint and Docker v2
# manifests -- each ruled out by inspecting the built image rather than guessed.
#
# The image is the one already in ECR. Nothing is rebuilt.
#
# HTTPS, via Caddy and Let's Encrypt on the same box. A certificate needs a
# domain, and the free one here is sslip.io: `13-232-84-149.sslip.io` resolves
# to 13.232.84.149 with no account, no record to create and nothing to renew,
# so the Elastic IP IS the hostname. Caddy terminates TLS, redirects 80 to 443
# and renews on its own. "Not Secure" in the address bar costs more than the
# hour this took.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
NAME="${EC2_NAME:-receipts-demo}"
# t3.small, not t3.micro.
#
# `unsettled_amount` — the heaviest metric in the layer, a join over
# payment_attempts and settlements — did not complete in FIVE MINUTES on a
# t3.micro, in English or Tanglish. It is one of the nine demo examples, so the
# demo had been unable to answer one of its own suggestions for
# global_finance and admin. It went unnoticed because every live check until now
# had used rm_tamil_nadu questions, which are light.
#
# 1GB is not enough for DuckDB to hold that join; 2GB answers it. The difference
# is about 20c a day.
TYPE="${EC2_TYPE:-t3.small}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
q() { aws "$@" --region "${REGION}"; }

teardown() {
  log "Tearing down"
  ids=$(q ec2 describe-instances --filters "Name=tag:Name,Values=${NAME}" \
        "Name=instance-state-name,Values=pending,running,stopping,stopped" \
        --query 'Reservations[].Instances[].InstanceId' --output text)
  [[ -n "${ids}" ]] && { q ec2 terminate-instances --instance-ids ${ids} >/dev/null
    echo "terminating ${ids}"; q ec2 wait instance-terminated --instance-ids ${ids}; }

  # Release the Elastic IP. An EIP is free while it is attached to a running
  # instance and BILLED HOURLY once it is not -- so the one state this script
  # must never leave behind is an address associated with nothing. Released
  # after the instance is gone, and before the script can exit for any other
  # reason.
  alloc=$(q ec2 describe-addresses --filters "Name=tag:Name,Values=${NAME}" \
          --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo None)
  if [[ -n "${alloc}" && "${alloc}" != "None" ]]; then
    echo "releasing Elastic IP ${alloc}"
    q ec2 release-address --allocation-id "${alloc}"
  fi
  q ec2 delete-security-group --group-name "${NAME}-sg" 2>/dev/null || true
  aws iam remove-role-from-instance-profile --instance-profile-name "${NAME}-profile" \
    --role-name "${NAME}-ec2-role" 2>/dev/null || true
  aws iam delete-instance-profile --instance-profile-name "${NAME}-profile" 2>/dev/null || true
  aws iam detach-role-policy --role-name "${NAME}-ec2-role" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly 2>/dev/null || true
  aws iam delete-role --role-name "${NAME}-ec2-role" 2>/dev/null || true
  echo "done. Nothing is running."
  exit 0
}
[[ "${1:-}" == "--teardown" ]] && teardown

TAG="$(git -C "${REPO_ROOT}" rev-parse --short=12 HEAD)"
IMAGE="${ECR}/${NAME}:${TAG}"
q ecr describe-images --repository-name "${NAME}" --image-ids "imageTag=${TAG}" >/dev/null 2>&1 \
  || { echo "no image ${IMAGE}; run deploy/aws/lambda.sh first (it builds and pushes)" >&2; exit 1; }
log "Using ${IMAGE}"

# --------------------------------------------------------------------------- #
# Instance profile, so the box can pull from ECR without a key on it.
# --------------------------------------------------------------------------- #
if ! aws iam get-role --role-name "${NAME}-ec2-role" >/dev/null 2>&1; then
  log "Creating the instance role"
  aws iam create-role --role-name "${NAME}-ec2-role" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "${NAME}-ec2-role" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
  aws iam create-instance-profile --instance-profile-name "${NAME}-profile" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "${NAME}-profile" \
    --role-name "${NAME}-ec2-role"
  echo "waiting for IAM to propagate"; sleep 20
fi

# --------------------------------------------------------------------------- #
# Security group: 80 in, from anywhere. Nothing else, and no SSH -- there is
# nothing to log in to and an open 22 is a standing invitation.
# --------------------------------------------------------------------------- #
if ! q ec2 describe-security-groups --group-names "${NAME}-sg" >/dev/null 2>&1; then
  log "Creating the security group"
  VPC=$(q ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
  q ec2 create-security-group --group-name "${NAME}-sg" --vpc-id "${VPC}" \
    --description "Receipts demo, 80 and 443" >/dev/null
  # 80 stays open: it is where ACME's HTTP-01 challenge lands, and Caddy
  # redirects everything else on it to 443.
  q ec2 authorize-security-group-ingress --group-name "${NAME}-sg" \
    --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null
  q ec2 authorize-security-group-ingress --group-name "${NAME}-sg" \
    --protocol tcp --port 443 --cidr 0.0.0.0/0 >/dev/null
fi

# --------------------------------------------------------------------------- #
# The Elastic IP comes FIRST, because the certificate's hostname is derived from
# it: sslip.io maps 13-232-84-149.sslip.io to 13.232.84.149, so the address is
# the domain and there is no DNS record to create. That also means the address
# has to be known before user-data is written, not after the instance is up.
#
# Reused if one is already tagged, so redeploying does not leak a second address
# and does not change the URL.
# --------------------------------------------------------------------------- #
ALLOC=$(q ec2 describe-addresses --filters "Name=tag:Name,Values=${NAME}" \
        --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo None)
if [[ -z "${ALLOC}" || "${ALLOC}" == "None" ]]; then
  log "Allocating an Elastic IP"
  ALLOC=$(q ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=${NAME}}]" \
    --query AllocationId --output text)
fi
IP=$(q ec2 describe-addresses --allocation-ids "${ALLOC}" \
     --query 'Addresses[0].PublicIp' --output text)
HOST="${IP//./-}.sslip.io"
log "Address ${IP}, hostname ${HOST}"

AMI=$(q ssm get-parameters --names \
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text)
log "AMI ${AMI}"

cat > "${REPO_ROOT}/.make/userdata.sh" <<UD
#!/bin/bash
set -x
dnf install -y docker
systemctl enable --now docker
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR}
docker pull ${IMAGE}

# The app no longer publishes a port. Caddy is the only thing on 80 and 443, and
# reaches the app by container name over a private network.
docker network create web || true
docker run -d --restart always --name receipts --network web \
  -e RECEIPTS_LLM_MODE=replay -e DEMO_MODE=true -e RECEIPTS_AUDIT_PATH=/tmp/audit.sqlite \
  ${IMAGE}

mkdir -p /etc/caddy
cat > /etc/caddy/Caddyfile <<'CADDY'
${HOST} {
	reverse_proxy receipts:7860
	encode gzip
}
CADDY

# caddy:2 from Docker Hub. Auto-HTTPS: it asks Let's Encrypt for ${HOST} over
# the HTTP-01 challenge on port 80, redirects 80 to 443 once it has the cert,
# and renews without being asked. The volumes keep the certificate and the
# account key across container restarts -- not across instance replacement,
# which is why a redeploy re-issues rather than reuses. LE allows that.
docker volume create caddy_data || true
docker run -d --restart always --name caddy --network web \
  -p 80:80 -p 443:443 \
  -v /etc/caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v caddy_data:/data \
  caddy:2
UD

# Replace, rather than accumulate. Re-running this script IS the redeploy path:
# it terminates the instance that is there and keeps the Elastic IP, so the URL
# survives. Going through `--teardown` first would release the address and hand
# back a different link -- which defeats the only reason the address exists.
old_ids=$(q ec2 describe-instances --filters "Name=tag:Name,Values=${NAME}" \
          "Name=instance-state-name,Values=pending,running,stopping,stopped" \
          --query 'Reservations[].Instances[].InstanceId' --output text)
if [[ -n "${old_ids}" ]]; then
  log "Replacing ${old_ids}"
  q ec2 terminate-instances --instance-ids ${old_ids} >/dev/null
  q ec2 wait instance-terminated --instance-ids ${old_ids}
fi

log "Launching ${TYPE}"
IID=$(q ec2 run-instances --image-id "${AMI}" --instance-type "${TYPE}" \
  --security-groups "${NAME}-sg" \
  --iam-instance-profile "Name=${NAME}-profile" \
  --user-data "file://${REPO_ROOT}/.make/userdata.sh" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${NAME}}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "instance ${IID}"
q ec2 wait instance-running --instance-ids "${IID}"

# --------------------------------------------------------------------------- #
# The Elastic IP, so the URL survives a redeploy.
#
# Without it the public DNS name is derived from whatever address the instance
# happens to get, and replacing the instance changes the URL -- which is fine
# for a throwaway and not fine for a link that goes in a README, a video and an
# application. Reused if one is already tagged, so redeploying does not leak a
# second address.
# --------------------------------------------------------------------------- #
log "Associating ${ALLOC}"
q ec2 associate-address --instance-id "${IID}" --allocation-id "${ALLOC}" >/dev/null

URL="https://${HOST}"
log "Waiting for the container (docker install + a 437MB pull) and the certificate"
ok=""
for i in $(seq 1 80); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${URL}/healthz" || echo 000)
  echo "  ${i}: ${code}"
  if [[ "${code}" == "200" ]]; then ok="yes"; break; fi
  sleep 15
done

if [[ -z "${ok}" ]]; then
  echo
  echo "HTTPS never answered 200. The box may be up with no certificate." >&2
  echo "Check plain HTTP, which is also what ACME uses:" >&2
  curl -s -o /dev/null -w '  http://%{host} -> %%{http_code}\n' --max-time 10 "http://${HOST}/healthz" >&2 || true
  echo "If HTTP works and HTTPS does not, Let's Encrypt refused the name." >&2
  exit 1
fi

# Say what the certificate actually is, rather than trusting that 200 meant TLS.
log "Certificate"
echo | openssl s_client -connect "${HOST}:443" -servername "${HOST}" 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates 2>/dev/null | sed 's/^/  /' || true

log "Live"
echo "${URL}"
echo "${URL}/?role=rm_tamil_nadu   <- try as the Chennai manager"
echo
echo "Tear it down with:  deploy/aws/ec2.sh --teardown"
echo "(that also releases the Elastic IP, which is billed once nothing holds it)"
