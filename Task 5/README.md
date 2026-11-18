# Task 5 | Shopping assistant

Ran locally with Python 3.10+, reading from BigQuery (sandbox project, dataset `retail_case`).
Every search reads `retail_case.products_enriched` (Task 3), which is the updated catalogue with `product_updates.csv` applied.
The project comes from your gcloud / application default credentials (`gcloud auth application-default login`).
Parsing is rule-based, with no paid services.

## Files

| File | What it does |
|---|---|
| `assistant.py` | Parser, BigQuery search and CLI |
| `app.py` | Flask web interface and JSON API on top of `assistant.py` |
| `static/index.html` | The search page |
| `test_assistant.py` | Unit tests for the parser and response logic (no BigQuery needed) |
| `assistant_output.txt` | CLI output for the demo queries |
| `web_ui_results.png`, `web_ui_no_results.png` | Screenshots of the web interface |

## Run

Prerequisite: `retail_case.products_enriched` exists (Task 3).

```sh
cd "Task 5"
pip install -r requirements.txt

python assistant.py                                   # demo queries (see assistant_output.txt)
python assistant.py "black handbag under AED 400"     # any query
python assistant.py "Tom Ford fragrance" --json       # raw JSON response

python app.py                                         # web interface on http://127.0.0.1:8000
python -m unittest -v test_assistant.py               # tests
```

The web page can also be opened with a query in the URL, for example `http://127.0.0.1:8000/?q=black+handbag+under+AED+400`.
The JSON API is `GET /api/search?q=<text>`.

## Demo results

| Query | Filters understood | Returned | Hidden (out of stock) |
|---|---|---|---|
| `black handbag under AED 400` | category Bags, colour Black, price < 400 | P009 Black crossbody bag AED 280, P002 Black mini handbag AED 320 | P008 Black shoulder bag (stock 0 after update) |
| `Tom Ford fragrance under AED 500` | brand Tom Ford, category Fragrance, price < 500 | P003 Amber eau de parfum AED 480 | - |
| `black handbag under AED 100` | category Bags, colour Black, price < 100 | No results message | - |
| `leather bag` | category Bags, word `leather` | P001 Black leather handbag AED 450 | P005 Leather tote |
| `perfume between AED 200 and 300` | category Fragrance, 200 <= price <= 300 | P004 Rose eau de parfum AED 290 | - |
| `red handbag` | category Bags, colour Red | No results message | - |

The updated catalogue shows up in the results: P009 exists only in the update file, P008 is now out of stock, and P001 keeps AED 450 because its negative-price update was rejected in Task 3.

## How a query is answered

1. **Vocabulary from BigQuery.**
   The distinct categories, brands, attributes and `search_text` words are read from `products_enriched`.
   A new brand or colour in the catalogue is understood without code changes.
   The vocabulary is cached for 5 minutes in the web app.
2. **Price phrases** are parsed first and removed from the text.
   Supported: `under / below / less than / <` (strict), `up to / at most / max / <=` (inclusive), `over / above / more than / >`, `at least / from / >=`, `between X and Y`, `X-Y`, with optional `AED`, `dhs` or `dirham` before or after the number.
   If several bounds are given, the tightest one wins.
3. **Catalogue phrases** are matched longest first, so `tom ford` and `brand a` win over single words.
   Generic words map to categories: `handbag`, `bag`, `purse` to Bags; `perfume`, `fragrance`, `scent` to Fragrance; `accessory` to Accessories.
4. **Leftover words:** stopwords (`show`, `me`, `a`, ...) are dropped.
   Common colour words are always a colour filter, so `red handbag` returns nothing instead of silently returning black handbags.
   Words that appear in `search_text` (for example `leather`, `silk`, `crossbody`) become required words, with simple plural handling (`scarves` to `scarf`).
   Anything else is reported back as ignored, so the user can see what was not understood.
5. **One parameterised BigQuery query** applies the filters (OR within a filter, AND across filters), restricted to `currency = 'AED'` and sorted by price.
   Query parameters are used instead of string formatting, so user input cannot change the SQL.
6. **Stock:** products with `stock <= 0` are never returned as results.
   They are listed separately as "hidden, out of stock", which makes the exclusion visible in the demo.
7. **No results:** the response says which filters were applied, for example `No in-stock products match category Bags, colour Black, price < AED 100.`
   A query with no recognisable terms (`hello`) gets a hint instead of the whole catalogue.