# ADR-022 — AWS EC2 for the demo, in replay mode

Status: accepted
Date: 2026-09-14

## Context

SDD §28 requires the demo to run "the same Compose stack on one small host or a
PaaS", with the choice recorded in an ADR. PDD §9's DevOps bar asks for a live
deployment with demo roles, and BUILD_PROMPTS M20 asks for `DEMO_MODE`, rate
limits, a daily spend cap and a one-click role link.

Two decisions were needed: where, and whether the deployed demo calls a model.

## Decision — where

**AWS EC2**, one `t3.micro` in `ap-south-1`, after four other hosts refused.

Recorded as a list because the reasons differ and each one is a fact about the
platform rather than about this project:

| host | why not |
|---|---|
| Fly.io | refuses to create an app without a card on file |
| Hugging Face Spaces | Docker Spaces now require PRO; only static Spaces are free, and a static Space cannot run FastAPI |
| AWS App Runner | `SubscriptionRequiredException` on this account |
| AWS Lightsail containers | quota-blocked at zero on this account |
| AWS Lambda | `Runtime.InvalidEntrypoint: ProcessPermissionDenied`, through four fixes |

The Lambda attempt is worth its own line because it was the best option on the
merits — HTTPS free, about two cents for a four-day demo, and the only free tier
of the five that is perpetual rather than promotional. Four candidate causes
were fixed and each was *ruled out by inspecting the built image* rather than
guessed at: OCI manifests (Lambda takes Docker v2 schema 2 only), the web
adapter's file mode, the non-root user, and a PATH-resolved entrypoint symlink.
The error did not move. It is left in the repository as `deploy/aws/lambda.sh`
and `Dockerfile.lambda`, working up to the point it stops working, rather than
deleted — the next person to try will get four hours back.

EC2 is the dull answer and it took ten minutes. One instance, port 80 open and
nothing else, no SSH, the image pulled from ECR by an instance role so no
credential sits on the box.

**HTTP, not HTTPS.** A certificate needs a domain name, and this is a demo
measured in days. Stated here and in the report rather than left for the browser
to announce.

The original choice was Fly, and `fly.toml` remains in the repository for
whenever a card exists. Nothing about the artifact changed across five hosts:
it is one container, and that was the point of ADR-008.

The artifact is a single container (ADR-008: the SPA ships inside the API
image), so the requirements are narrow: run one container, give it a few GB of
disk for the generated warehouse, terminate TLS, and cost nothing when nobody is
looking. Fly does all four, and `auto_stop_machines` means an idle demo is free.

The alternatives were rejected on the volume, not on price. The warehouse is a
~1 GB DuckDB file that `make data` generates in about three and a half minutes;
a platform with only ephemeral disk would have to rebuild it on every cold start
or bake it into the image. Baking it in would put a generated artifact in the
image and break the rule that `data/` is never committed.

Nothing about this choice is load-bearing. The deployable is a Dockerfile; moving
it is a different `fly.toml`.

## Decision — the deployed demo runs in REPLAY mode

`RECEIPTS_LLM_MODE=replay`. The demo makes **no model calls and costs nothing
per question**.

BUILD_PROMPTS M20 says "live model mode, recording off", and this departs from
it deliberately:

1. **The recordings are the measured system.** Every number in the report came
   from these exact responses. A reviewer clicking an example question sees the
   answer that was scored, not a fresh sample from a model that may answer
   differently today. For a demo whose entire argument is reproducibility, that
   is the stronger position.
2. **It cannot spend anyone's money.** `ReplayLLM` holds no network client, so a
   missing recording raises rather than falling through to a provider. A public
   URL with a live key behind it is an invitation to spend; a public URL with no
   key is not.
3. **The key that recorded them should be rotated** (HANDOFF §3), and deploying
   it publicly is the opposite of rotating it.

**What this costs:** a question outside the recorded set returns
`MODEL_UNAVAILABLE` rather than an answer. The UI says so before the reviewer
types — the note beside the input, in all three languages — and the example
questions per role are generated from the recorded set so they always work.

The live path is not dead code: `make bench MODE=live` exercises it, and
flipping the deployment to live is one environment variable plus a key.

## Consequences

- Demo login, the per-minute rate limit and the daily spend cap are all gated on
  `DEMO_MODE`, which is true on this deployment and false by default elsewhere.
- The spend cap is enforced and, in replay, will never be reached. It is there
  so that flipping to live is a one-variable change and not a redesign.
- The one-click link is `?role=<name>`, handled by the SPA with no router.
- Observability is console spans plus the in-app ReceiptDrawer. Jaeger and
  Grafana are cut (PDD §13 item 2); `OTEL_EXPORTER_OTLP_ENDPOINT` switches the
  exporter if a collector ever exists.
