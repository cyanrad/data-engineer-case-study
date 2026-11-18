-- Step 1b (GCP): streaming tables. Run by setup_gcp.sh; safe to re-run.

-- One row per event_id. Partitioned by EVENT time, so late events land in the day they happened.
CREATE TABLE IF NOT EXISTS retail_case.events_stream (
  event_id         STRING    NOT NULL,
  event_date       STRING,
  event_timestamp  INT64     NOT NULL,
  event_ts         TIMESTAMP NOT NULL,
  event_name       STRING    NOT NULL,
  user_pseudo_id   STRING    NOT NULL,
  user_id          STRING,
  event_params     ARRAY<STRUCT<key STRING, value STRUCT<string_value STRING, int_value INT64>>>,
  user_properties  ARRAY<STRUCT<key STRING, value STRUCT<string_value STRING, int_value INT64>>>,
  items            ARRAY<STRUCT<item_id STRING, quantity INT64, price FLOAT64>>,
  ingested_at      TIMESTAMP
)
PARTITION BY DATE(event_ts)
CLUSTER BY event_id;

-- Rejected messages with the reasons.
CREATE TABLE IF NOT EXISTS retail_case.events_dead_letter (
  raw_payload  STRING,
  errors       ARRAY<STRING>,
  received_at  TIMESTAMP
);
