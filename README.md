# Retail data platform | Data Engineering case study

GA4-style events and product data turned into clean BigQuery tables, a streaming pipeline, an enriched catalogue, recommendations and a shopping assistant.
Everything runs on BigQuery (dataset `retail_case`) in a personal GCP free-trial project.
Each task folder has its own README with details, sample output and limitations.

| Folder | Task | Ran in |
|---|---|---|
| `Task 1/` | GA4 ingestion: `events_clean`, `event_items`, views/purchases per SKU, abandoned carts | BigQuery |
| `Task 2/` | Streaming: Pub/Sub publisher and consumer writing to BigQuery | GCP (Pub/Sub + BigQuery) |
| `Task 3/` | Product feed: incremental updates and `products_enriched` | BigQuery |
| `Task 4/` | Recommendations | Python locally, reads BigQuery |
| `Task 5/` | Shopping assistant with CLI and web interface | Python locally, reads BigQuery |
| `data/` | Input fixtures | - |

![Shopping assistant web interface](Task%205/web_ui_results.png)

## Setup

Needs Python 3.10+, the Google Cloud SDK and a GCP project with BigQuery and Pub/Sub enabled.

```sh
gcloud auth application-default login
gcloud config set project <your-project>
pip install -r requirements.txt

bq --location=US mk --dataset retail_case
bq --location=US load --source_format=NEWLINE_DELIMITED_JSON retail_case.events_daily data/events_daily.jsonl data/ga4_schema.json
bq --location=US load --source_format=NEWLINE_DELIMITED_JSON retail_case.events_intraday data/events_intraday.jsonl data/ga4_schema.json
bq --location=US load --source_format=CSV --skip_leading_rows=1 retail_case.products_raw data/products.csv product_id:STRING,name:STRING,brand:STRING,category:STRING,price:FLOAT,stock:INTEGER,attribute:STRING,currency:STRING,updated_at:TIMESTAMP
```

## Run
Run the tasks in order: 1, then 2 and 3, then 4 and 5.
The exact commands are in each task's README.
Quick start for the assistant:

```sh
cd "Task 5"
python app.py                                 # web interface on http://127.0.0.1:8000
python assistant.py "black handbag under AED 400"
```

## Limitations

- Task 6 (GCP organisation and DevOps) is not done, so there is no CI.
- The streaming consumer runs in replay mode and is at-least-once with dedup, not exactly-once.
- Only Task 5 has automated tests; the other tasks were checked by running them against BigQuery.
