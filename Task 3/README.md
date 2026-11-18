# Task 3 | Product feed

Ran in BigQuery (sandbox project, dataset `retail_case`).

## Files

| Step | File | What it does | Sample output |
|---|---|---|---|
| 1 | `bq load` (below) | Loads `data/product_updates.csv` into `retail_case.products_inc` | - |
| 2 | `product_upsert.sql` | Copies `products_raw` into `products_tmp` and merges the valid updates into it | `product_upsert_output.csv` |
| 3 | `products_enriched.sql` | Builds `products_enriched` from `products_tmp` and `event_items` | `products_enriched_output.csv` |
| 4 | `rerun_validation.sql` | Applies the same update a second time and checks the row count does not change | - |

## Run

Prerequisites: `retail_case.products_raw` is loaded (see the root README) and `retail_case.event_items` exists (Task 1).

```sh
cd "Task 3"
# step 1, once
bq --location=US load --source_format=CSV --skip_leading_rows=1 retail_case.products_inc ../data/product_updates.csv product_id:STRING,name:STRING,brand:STRING,category:STRING,price:FLOAT,stock:INTEGER,attribute:STRING,currency:STRING,updated_at:TIMESTAMP
bq query --use_legacy_sql=false < product_upsert.sql         # step 2
bq query --use_legacy_sql=false < products_enriched.sql      # step 3
bq query --use_legacy_sql=false < rerun_validation.sql       # step 4, prints 'the count matches'
```

Step 1 appends rows, so run it only once (or drop `products_inc` first).
Steps 2 to 4 rebuild their tables, so they can be re-run safely.

## Incremental update

`product_upsert.sql` runs a `MERGE` from `products_inc` into `products_tmp` on `product_id`:

1. Rows with `price < 0` or `stock < 0` are rejected before anything else.
2. The newest remaining row per `product_id` is kept (`QUALIFY ROW_NUMBER() ... ORDER BY updated_at DESC`), so this is the newest valid row.
3. A matched product is updated only if the incoming `updated_at` is newer than the stored one.
4. An unknown product is inserted.

A rejected row never reaches the `MERGE`, so the previous valid record stays in place.
`products_tmp` is a copy of `products_raw`, so the raw load is never modified and the step is reproducible.

## products_enriched schema

One row per `product_id` (9 rows).

| Column | Type | Description |
|---|---|---|
| `product_id` | STRING | Unique key |
| `name` | STRING | Product name |
| `brand` | STRING | Brand |
| `category` | STRING | Category (Bags, Fragrance, Accessories) |
| `price` | FLOAT64 | Current price, never negative |
| `currency` | STRING | Currency code (AED) |
| `stock` | INT64 | Units in stock, never negative |
| `attribute` | STRING | Colour or scent |
| `availability` | STRING | `in_stock` if `stock > 0`, otherwise `out_of_stock` |
| `search_text` | STRING | `name brand category attribute`, NFKC-normalised, lowercased, punctuation stripped, whitespace collapsed |
| `view_count` | INT64 | Number of `view_item` events for the SKU, 0 if none |
| `purchased_quantity` | INT64 | Sum of purchased `item_quantity` for the SKU, 0 if none |
| `updated_at` | TIMESTAMP | Timestamp of the row version that was kept |

`view_count` and `purchased_quantity` come from `event_items` (Task 1), which is built only from the daily and intraday batch files.
Streamed events from Task 2 (`events_stream`) are not included, so these counts are the original batch snapshot.

## Quality checks

| Check | Where | Result |
|---|---|---|
| No negative price or stock | Last query in `product_upsert.sql` (returns the offending `product_id`s) | 0 rows |
| Re-running the update creates no extra rows | `rerun_validation.sql` (applies the update again to a copy and compares counts) | `the count matches` (9 = 9) |
| One row per `product_id` | `SELECT COUNT(*), COUNT(DISTINCT product_id) FROM retail_case.products_enriched` | 9, 9 |
| Invalid update keeps the previous record | P001 in `products_enriched` | price 450, `updated_at` 2026-01-10 |
| Products with no events still appear | `LEFT JOIN` + `COALESCE(..., 0)` | P005 and P009 have 0 views and 0 purchases |