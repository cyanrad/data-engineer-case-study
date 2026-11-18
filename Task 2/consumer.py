"""Step 3 - Consumer: pull from Pub/Sub, validate, skip repeats, write to BigQuery.

    python consumer.py            # uses the gcloud project (or GCP_PROJECT if set)

- Malformed messages go to retail_case.events_dead_letter with the reasons.
- An event_id seen before (earlier in this run, in an earlier replay, or in the batch tables
  events_daily / events_intraday) is skipped, so a replay never adds rows twice.
- Late events are accepted. Rows carry event_ts (event time) and the table is partitioned on it,
  so arrival order does not matter.
- A batch is acked only after its write succeeded. If the write fails the batch is handed back for
  redelivery by Pub/Sub (to the dead-letter topic after 5 attempts).
"""

import collections

from common import DATASET, PROJECT, SUBSCRIPTION, to_row, utc_now, validate


class GcpStore:
    """Pub/Sub pull subscription in, BigQuery tables out."""

    def __init__(self):
        from google.cloud import bigquery, pubsub_v1

        self.bq = bigquery.Client(project=PROJECT)
        self.sub = pubsub_v1.SubscriberClient()
        self.path = self.sub.subscription_path(PROJECT, SUBSCRIPTION)

    def pull(self) -> list[tuple[str, bytes]]:
        """Up to 100 (ack_id, message body) pairs, or [] once the subscription is drained."""
        from google.api_core.exceptions import DeadlineExceeded

        for _ in range(3):  # a pull can come back empty while messages remain, so try a few times
            try:
                received = self.sub.pull(
                    request={"subscription": self.path, "max_messages": 100}, timeout=10).received_messages
            except DeadlineExceeded:
                received = []
            if received:
                return [(m.ack_id, m.message.data) for m in received]
        return []

    def ack(self, ack_ids: list[str]) -> None:
        self.sub.acknowledge(request={"subscription": self.path, "ack_ids": ack_ids})

    def redeliver(self, ack_ids: list[str]) -> None:
        # Deadline 0 makes Pub/Sub redeliver (with the subscription's retry backoff).
        self.sub.modify_ack_deadline(
            request={"subscription": self.path, "ack_ids": ack_ids, "ack_deadline_seconds": 0})

    def existing_ids(self) -> set[str]:
        sql = f"""SELECT event_id FROM `{PROJECT}.{DATASET}.events_stream`
                  UNION DISTINCT SELECT event_id FROM `{PROJECT}.{DATASET}.events_daily`
                  UNION DISTINCT SELECT event_id FROM `{PROJECT}.{DATASET}.events_intraday`"""
        return {row.event_id for row in self.bq.query(sql).result()}

    def write(self, rows: list[dict], dead: list[dict]) -> None:
        # Passing event_id as the row id adds BigQuery's best-effort dedup on top of existing_ids.
        self._insert("events_stream", rows, row_ids=[row["event_id"] for row in rows])
        self._insert("events_dead_letter", dead)

    def _insert(self, table: str, rows: list[dict], row_ids: list[str] | None = None) -> None:
        if not rows:
            return
        errors = self.bq.insert_rows_json(f"{PROJECT}.{DATASET}.{table}", rows, row_ids=row_ids)
        if errors:
            raise RuntimeError(f"insert into {table} failed: {errors}")

    def row_count(self) -> int:
        sql = f"SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET}.events_stream`"
        return next(iter(self.bq.query(sql).result())).n


def run() -> dict:
    store = GcpStore()
    seen = store.existing_ids()
    counts = collections.Counter(received=0, inserted=0, duplicates_skipped=0, dead_lettered=0, late_arrivals=0)
    latest_ts = 0
    while batch := store.pull():
        ack_ids = [ack_id for ack_id, _ in batch]
        rows, dead, new_ids = [], [], set()
        for _, raw in batch:
            counts["received"] += 1
            event, errors = validate(raw)
            if errors:
                dead.append({"raw_payload": raw.decode("utf-8", "replace"), "errors": errors, "received_at": utc_now()})
                counts["dead_lettered"] += 1
                continue
            if event["event_timestamp"] < latest_ts:  # arrived after a newer event: accept it anyway
                counts["late_arrivals"] += 1
            latest_ts = max(latest_ts, event["event_timestamp"])
            if event["event_id"] in seen or event["event_id"] in new_ids:
                counts["duplicates_skipped"] += 1
            else:
                new_ids.add(event["event_id"])
                rows.append(to_row(event))
                counts["inserted"] += 1
        try:
            store.write(rows, dead)
        except Exception:
            store.redeliver(ack_ids)
            raise
        store.ack(ack_ids)
        seen |= new_ids
    return {**counts, "events_stream_total_rows": store.row_count()}


if __name__ == "__main__":
    for key, value in run().items():
        print(f"{key:<26}{value}")
