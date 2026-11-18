# Task 2 | Streaming to BigQuery

Ran in GCP (sandbox project): Pub/Sub topic and subscription, Python publisher and consumer, BigQuery tables.

## Files

| Step | File | What it does |
|---|---|---|
| 1 | `setup_gcp.sh` + `create_tables.sql` | Pub/Sub topic, subscription, dead-letter topic and BigQuery tables |
| 2 | `publisher.py` | Publishes each line of `data/stream_events.jsonl` as one message |
| 3 | `consumer.py` | Pulls, validates, skips repeats, writes to `events_stream` / `events_dead_letter` |
| 4 | `check_counts.sql` | Verifies the BigQuery tables after the replays |
| - | `common.py` | Shared settings and validation |

## Run

Prerequisite: `retail_case.events_daily` and `retail_case.events_intraday` are loaded (root README), since the consumer dedupes against them.

```sh
pip install -r requirements.txt
gcloud config set project <your-project>
gcloud auth application-default login
bash setup_gcp.sh                                     # step 1, once
python publisher.py && python consumer.py             # replay 1
python publisher.py && python consumer.py             # replay 2
bq query --use_legacy_sql=false < check_counts.sql    # step 4
```

## Expected output (two replays)

Counts printed by `consumer.py`:

| | Replay 1 | Replay 2 |
|---|---|---|
| received | 4 | 4 |
| inserted | 1 (E15) | 0 |
| duplicates_skipped | 2 (E14 twice, already in `events_intraday`) | 3 (E14 twice + E15) |
| dead_lettered | 1 (BAD1) | 1 (BAD1) |
| late_arrivals | 1 (E15 is older than E14 but arrives after it) | 1 |
| events_stream_total_rows | 1 | 1 |

State in BigQuery after both replays (`check_counts.sql`):

- `events_stream`: 1 row, 1 distinct id (E15, stored at its event time `2026-01-10 00:12:59` UTC).
- `events_dead_letter`: 2 rows, one BAD1 per replay, reason `missing event_timestamp; missing user_pseudo_id`.
- Overlap between `events_stream` and the batch tables: 0.

## How the requirements are met

- **Validation:** `event_id`, `event_name` and `user_pseudo_id` must be non-empty strings and `event_timestamp` an integer.
  Anything else, including invalid JSON, goes to `events_dead_letter` with the reasons.
- **Repeats:** at start the consumer loads every `event_id` already in `events_stream`, `events_daily` and `events_intraday`, and skips any event in that set or seen earlier in the run.
  The BigQuery insert also passes `event_id` as the insert id for best-effort dedup.
- **Late events:** nothing is dropped for being late.
  Rows store `event_ts` (from `event_timestamp`) and `events_stream` is partitioned by `DATE(event_ts)`, so arrival order does not matter.
- **Retries:** a batch is acked only after its BigQuery write succeeds.
  If the write fails the batch is nacked and Pub/Sub redelivers it with 10s to 600s backoff.
  After 5 failed attempts the message moves to the `ga4-events-dlq` topic.
  The publisher client retries transient publish errors itself.
- **Delivery semantics:** Pub/Sub delivers at least once.
  Skipping known ids makes the results idempotent, but this is **not** exactly-once delivery.

## Monitoring (production)

- Alert on `subscription/oldest_unacked_message_age` and `num_undelivered_messages` (consumer falling behind).
- Alert on messages in `ga4-events-dlq-sub` and new rows in `events_dead_letter` (bad producers or schema drift).
- Log-based metrics for the consumer counts and insert errors.
- Daily check that `events_stream` has no duplicate `event_id`s and no overlap with the batch tables.

## Production scaling

- Run the consumer as a long-running service (Cloud Run or GKE with streaming pull), or as a Dataflow streaming job for high volume.
- With several consumers the in-memory id set no longer catches all repeats, so write to a staging table and `MERGE` into `events_stream` on `event_id`.
- Use the BigQuery Storage Write API instead of legacy streaming inserts (cheaper, higher throughput).
- Limit the dedup lookup to recent event dates (for example 7 days) instead of loading every id.

## Limitations

- Validation covers the four required fields only.
  A wrong type in a nested field (for example `items.quantity` as a string) fails the BigQuery insert, so the message ends up in the Pub/Sub dead-letter topic rather than `events_dead_letter`.
- The consumer runs in replay mode: it stops once the subscription is empty.
- There are no automated tests.
