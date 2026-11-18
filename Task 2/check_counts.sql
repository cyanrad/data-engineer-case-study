-- Step 4 (GCP): run after each replay.
-- bq query --use_legacy_sql=false < check_counts.sql

-- Should stay at 1 row / 1 distinct id (E15) no matter how many replays.
SELECT COUNT(*) AS stream_rows, COUNT(DISTINCT event_id) AS distinct_event_ids
  FROM retail_case.events_stream;

-- E15 is stored with its event time (00:12:59 UTC) even though it arrived after E14 (00:14:00).
SELECT event_id, event_ts, event_name, user_pseudo_id, ingested_at
  FROM retail_case.events_stream
 ORDER BY event_ts;

-- One BAD1 row per replay.
SELECT received_at, errors, raw_payload
  FROM retail_case.events_dead_letter
 ORDER BY received_at;

-- Must be 0: nothing in the stream table duplicates the batch tables.
SELECT COUNT(*) AS overlap_with_batch
  FROM retail_case.events_stream
 WHERE event_id IN (SELECT event_id FROM retail_case.events_daily
                    UNION ALL
                    SELECT event_id FROM retail_case.events_intraday);
