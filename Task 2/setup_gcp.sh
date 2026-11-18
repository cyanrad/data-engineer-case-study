#!/usr/bin/env bash
# Uses the project currently set in gcloud (gcloud config get-value project).
# Safe to re-run: anything that already exists is skipped.
set -euo pipefail

topic() {
  if gcloud pubsub topics describe "$1" >/dev/null 2>&1; then
    echo "topic $1 already exists, skipping"
  else
    gcloud pubsub topics create "$1"
  fi
}

subscription() {
  local name="$1"; shift
  if gcloud pubsub subscriptions describe "$name" >/dev/null 2>&1; then
    echo "subscription $name already exists, skipping"
  else
    gcloud pubsub subscriptions create "$name" "$@"
  fi
}

topic ga4-events
# dead letting topic
topic ga4-events-dlq

# Subs
subscription ga4-events-dlq-sub --topic ga4-events-dlq
subscription ga4-events-consumer --topic ga4-events \
  --ack-deadline 60 --min-retry-delay 10s --max-retry-delay 600s \
  --dead-letter-topic ga4-events-dlq --max-delivery-attempts 5

# IAM access (adding a binding that already exists is a no-op)
# Let the Pub/Sub service agent move messages that failed 5 times to the dead-letter topic.
N=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
AGENT="serviceAccount:service-$N@gcp-sa-pubsub.iam.gserviceaccount.com"
gcloud pubsub topics add-iam-policy-binding ga4-events-dlq --member "$AGENT" --role roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions add-iam-policy-binding ga4-events-consumer --member "$AGENT" --role roles/pubsub.subscriber >/dev/null

# Tables use CREATE TABLE IF NOT EXISTS, so existing tables and their data are left alone.
bq query --use_legacy_sql=false < create_tables.sql
