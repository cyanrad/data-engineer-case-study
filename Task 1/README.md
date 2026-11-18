# Task 1 | GA4 ingestion and nested SQL

Ran in BigQuery (Used the free trial on new accounts)

## Files

| Step | File | What it does | Sample output |
|---|---|---|---|
| 1 | `events_clean.sql` | Merges daily + intraday, one row per `event_id`, flattens session, page, market and customer key | `events_clean_output.csv` |
| 2 | `event_items.sql` | Unnests `items`, one row per event item with `item_offset` | `event_items_output.csv` |
| 3 | `purchase_and_view_count.sql` | Views and purchased quantity per SKU | `purchase_and_view_count_output.csv` |
| 4 | `abandoned_carts.sql` | Customer / SKU pairs with an `add_to_cart` and no later purchase | `abandoned_carts_output.csv` |

## Run

Prerequisite: `retail_case.events_daily` and `retail_case.events_intraday` are loaded (see the root README).

```sh
cd "Task 1"
bq query --use_legacy_sql=false < events_clean.sql
bq query --use_legacy_sql=false < event_items.sql
bq query --use_legacy_sql=false --format=csv < purchase_and_view_count.sql
bq query --use_legacy_sql=false --format=csv < abandoned_carts.sql
```

Steps 1 and 2 rebuild their tables (`DROP` + `CREATE`), so they can be re-run safely.
Step 2 reads from step 1, and Tasks 3 and 4 read from step 2.

## events_clean

| Column | Type | Source |
|---|---|---|
| `event_id` | STRING | `event_id` (unique key) |
| `date_event` | DATE | `event_timestamp` converted to `Asia/Dubai` |
| `event_name` | STRING | `event_name` |
| `user_id` | STRING | Customer key: `user_id`, falling back to `user_pseudo_id`, then `'anon'` |
| `ga_session_id` | INT64 | `event_params` key `ga_session_id` |
| `page_url` | STRING | `event_params` key `page_location` |
| `market` | STRING | `user_properties` key `market` |
| `item_count` | INT64 | `ARRAY_LENGTH(items)`, 0 for itemless events |
| `items` | ARRAY<STRUCT> | Original `items` array, kept for `event_items` |
| `time_event_local` | DATETIME | `event_timestamp` in `Asia/Dubai` |

Itemless events are kept: E12 (`search`) is in `events_clean` with `item_count = 0`.

## event_items

`events_clean` cross joined with `UNNEST(items) WITH OFFSET AS item_offset`.
Columns: the event-level fields above plus `item_id`, `item_offset`, `item_quantity` and `item_price`.
Itemless events have no item rows, so they do not appear here by design.
`item_offset` is the item's position in the original array (E03 has P001 at 0 and P007 at 1).

## Daily / intraday reconciliation

In GA4, `events_intraday_YYYYMMDD` is a provisional table that fills during the day, and `events_YYYYMMDD` is the finalised daily export that replaces it.
The two fixture files overlap to simulate this:

- E09 and E10 are in both files, with identical content.
- E11 appears twice inside the intraday file.
- E11 to E14 exist only in intraday (not yet in a daily export).

`events_clean` unions both sources, tags each row with a `source_priority` (daily = 1, intraday = 2) and keeps one row per `event_id` with:

```sql
QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp DESC, source_priority DESC) = 1
```

Result: 17 raw rows (10 daily + 7 intraday) become 14 unique events.
A `GROUP BY ALL` would also work on this data, but would produce duplicates as soon as one non-key column differs between the two sources.

In production the daily export is the authoritative version, so I would put `source_priority` first in the `ORDER BY` and give daily the higher priority.
Once the daily table for a date lands, that date's intraday rows can be dropped.

## Partitioning (production)

The fixture is tiny, so the tables here are not partitioned.
For real volumes:

- Partition `events_clean` and `event_items` by `date_event` (daily partitions), with `require_partition_filter` so queries cannot scan the full history by accident.
- Cluster `events_clean` by `event_name, user_id` and `event_items` by `item_id, event_name`, which match the filters and joins used in Tasks 1, 3 and 4.
- Load incrementally instead of rebuilding everything: reprocess only the dates touched by the new daily or intraday data, and `MERGE` on `event_id` (or replace those partitions).
- Use a short lookback (for example 3 days) to pick up late-arriving events.
- Choose one timezone for `date_event` and use it everywhere.
  Here it is `Asia/Dubai`, since the market is AE.

## Abandoned cart rule

For each customer and SKU, the query finds the latest purchase time.
An `add_to_cart` is abandoned if there is no purchase of that SKU by that customer, or if the `add_to_cart` happened after the latest purchase (add, buy, add again).
The window is the whole supplied dataset.
