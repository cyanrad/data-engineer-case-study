"""Task 5 - Shopping assistant: natural language in, real catalogue products out.

    python assistant.py                                   # demo queries
    python assistant.py "black handbag under AED 400"     # any query
    python assistant.py "Tom Ford fragrance" --json       # raw JSON response

Reads from BigQuery (dataset retail_case, project from gcloud / application default credentials):
    - products_enriched (Task 3): the updated catalogue (product_updates.csv applied)

How a query is answered:
    1. The parser vocabulary (categories, brands, colours/attributes, search terms) is read from
       products_enriched, so new brands or colours in the catalogue are understood without code changes.
    2. The query is parsed with rules: price phrases ("under AED 400", "between 200 and 300"),
       then catalogue phrases (longest first), then category synonyms ("handbag" -> Bags).
    3. The filters run as one parameterised BigQuery query against products_enriched.
    4. Out-of-stock matches are never returned; they are listed separately so the exclusion is visible.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field

from google.cloud import bigquery

DATASET = "retail_case"
TABLE = f"{DATASET}.products_enriched"
CURRENCY = "AED"
VOCABULARY_TTL_SECONDS = 300
MAX_QUERY_LENGTH = 200

DEMO_QUERIES = [
    "black handbag under AED 400",        # category + colour + price, P008 hidden (out of stock)
    "Tom Ford fragrance under AED 500",   # brand + category + price
    "black handbag under AED 100",        # no results
    "leather bag",                        # free-text term, P005 hidden (out of stock)
    "perfume between AED 200 and 300",    # price range
    "red handbag",                        # colour that is not in the catalogue
]

# Generic words that mean a catalogue category. Only used when that category exists in the catalogue.
CATEGORY_SYNONYMS = {
    "bags": {"bag", "bags", "handbag", "handbags", "purse", "purses"},
    "fragrance": {"fragrance", "fragrances", "perfume", "perfumes", "parfum", "scent", "scents", "cologne"},
    "accessories": {"accessory", "accessories"},
}

# Colour words are always treated as a colour filter, even if no product has that colour.
# Otherwise "red handbag" would silently ignore "red" and return black handbags.
COLOUR_WORDS = {
    "black", "white", "red", "blue", "green", "brown", "beige", "pink", "grey", "gray", "navy",
    "gold", "silver", "yellow", "orange", "purple", "tan", "cream", "burgundy", "nude",
}

STOPWORDS = {
    "a", "an", "the", "i", "im", "me", "my", "we", "you", "want", "wanted", "need", "looking", "look",
    "search", "searching", "for", "show", "find", "get", "give", "buy", "some", "any", "please", "in",
    "with", "and", "or", "of", "to", "that", "is", "are", "it", "something", "item", "items", "product",
    "products", "price", "priced", "cost", "costs", "costing", "aed", "dhs", "dh", "dirham", "dirhams",
    "under", "below", "less", "than", "over", "above", "more", "cheap", "cheaper", "nice", "new", "can",
    "do", "have", "has", "what", "which", "there", "on", "at", "by", "from", "between", "up",
}

_AMOUNT = r"(?:(?:aed|dhs?|dirhams?)\s*)?\d[\d,]*(?:\.\d+)?(?:\s*(?:aed|dhs?|dirhams?)\b)?"
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# (pattern, kind). Order matters: ranges before single bounds, inclusive before strict.
PRICE_RULES = [
    (rf"\b(?:between|from)\s+{_AMOUNT}\s+(?:and|to)\s+{_AMOUNT}", "range"),
    (rf"{_AMOUNT}\s*(?:-|to)\s*{_AMOUNT}", "range"),
    (rf"(?:\b(?:up to|upto|at most|max(?:imum)?|no more than|not more than|within)\b|<=)\s*{_AMOUNT}", "max_inclusive"),
    (rf"(?:\b(?:under|below|less than|cheaper than)\b|<)\s*{_AMOUNT}", "max"),
    (rf"(?:\b(?:at least|min(?:imum)?|from|starting at|no less than)\b|>=)\s*{_AMOUNT}", "min_inclusive"),
    (rf"(?:\b(?:over|above|more than|greater than|pricier than)\b|>)\s*{_AMOUNT}", "min"),
]

SEARCH_SQL = f"""
SELECT  product_id, name, brand, category, attribute, price, currency, stock
  FROM  `{TABLE}`
 WHERE  currency = @currency
   -- BigQuery passes an empty array parameter as NULL, so NULL means "no filter"
   AND  (@categories IS NULL OR category  IN UNNEST(@categories))
   AND  (@brands     IS NULL OR brand     IN UNNEST(@brands))
   AND  (@attributes IS NULL OR attribute IN UNNEST(@attributes))
   AND  (@min_price IS NULL OR price > @min_price OR (@min_inclusive AND price = @min_price))
   AND  (@max_price IS NULL OR price < @max_price OR (@max_inclusive AND price = @max_price))
   -- every keyword must be a whole word of search_text
   AND  NOT EXISTS (SELECT 1 FROM UNNEST(@keywords) AS kw WHERE kw NOT IN UNNEST(SPLIT(search_text, ' ')))
 ORDER  BY price, product_id
"""

VOCABULARY_SQL = f"SELECT DISTINCT category, brand, attribute, search_text FROM `{TABLE}`"


def normalize(text: str) -> str:
    """Same normalisation as products_enriched.search_text: NFKC, lowercase, punctuation to spaces."""
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    if word.endswith("es") and word[:-2].endswith(("s", "x", "ch", "sh")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


@dataclass(frozen=True)
class Vocabulary:
    categories: tuple[str, ...]
    brands: tuple[str, ...]
    attributes: tuple[str, ...]
    terms: frozenset[str]

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "Vocabulary":
        def distinct(key: str) -> tuple[str, ...]:
            return tuple(sorted({r[key] for r in rows if r.get(key)}))

        terms = frozenset(t for r in rows for t in (r.get("search_text") or "").split())
        return cls(distinct("category"), distinct("brand"), distinct("attribute"), terms)

    def phrases(self) -> dict[tuple[str, ...], tuple[str, str]]:
        """Token sequence -> (filter field, catalogue value)."""
        out: dict[tuple[str, ...], tuple[str, str]] = {}
        for category in self.categories:
            key = normalize(category)
            for word in {key, singular(key)} | CATEGORY_SYNONYMS.get(key, set()):
                out[tuple(word.split())] = ("categories", category)
        for attribute in self.attributes:
            out[tuple(normalize(attribute).split())] = ("attributes", attribute)
        for brand in self.brands:
            out[tuple(normalize(brand).split())] = ("brands", brand)
        return out


@dataclass
class Filters:
    categories: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    min_price: float | None = None
    min_inclusive: bool = True
    max_price: float | None = None
    max_inclusive: bool = True
    ignored: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.categories or self.brands or self.attributes or self.keywords
                    or self.min_price is not None or self.max_price is not None)

    def add(self, name: str, value: str) -> None:
        values = getattr(self, name)
        if value not in values:
            values.append(value)

    def set_max(self, value: float, inclusive: bool) -> None:
        """Keep the tightest upper bound if several are given."""
        if self.max_price is None or value < self.max_price or (value == self.max_price and not inclusive):
            self.max_price, self.max_inclusive = value, inclusive

    def set_min(self, value: float, inclusive: bool) -> None:
        """Keep the tightest lower bound if several are given."""
        if self.min_price is None or value > self.min_price or (value == self.min_price and not inclusive):
            self.min_price, self.min_inclusive = value, inclusive

    def describe(self) -> str:
        parts = []
        if self.categories:
            parts.append("category " + " or ".join(self.categories))
        if self.brands:
            parts.append("brand " + " or ".join(self.brands))
        if self.attributes:
            parts.append("colour " + " or ".join(self.attributes))
        if self.keywords:
            parts.append("matching " + ", ".join(f"'{k}'" for k in self.keywords))
        if self.min_price is not None:
            parts.append(f"price {'>=' if self.min_inclusive else '>'} {format_price(self.min_price)}")
        if self.max_price is not None:
            parts.append(f"price {'<=' if self.max_inclusive else '<'} {format_price(self.max_price)}")
        return ", ".join(parts)


def format_price(value: float, currency: str = CURRENCY) -> str:
    return f"{currency} {value:,.0f}" if float(value).is_integer() else f"{currency} {value:,.2f}"


def _parse_prices(text: str, filters: Filters) -> str:
    """Apply every price phrase to filters and return the text with those phrases removed."""
    for pattern, kind in PRICE_RULES:
        def apply(match: re.Match) -> str:
            numbers = [float(n.replace(",", "")) for n in _NUMBER.findall(match.group(0))]
            if kind == "range":
                low, high = sorted(numbers[:2])
                filters.set_min(low, inclusive=True)
                filters.set_max(high, inclusive=True)
            elif kind.startswith("max"):
                filters.set_max(numbers[0], inclusive=kind.endswith("inclusive"))
            else:
                filters.set_min(numbers[0], inclusive=kind.endswith("inclusive"))
            return " "

        text = re.sub(pattern, apply, text)
    return text


def parse(query: str, vocabulary: Vocabulary) -> Filters:
    filters = Filters()
    text = _parse_prices(unicodedata.normalize("NFKC", query).lower(), filters)
    tokens = normalize(text).split()

    phrases = vocabulary.phrases()
    longest = max((len(p) for p in phrases), default=1)
    i = 0
    while i < len(tokens):
        for n in range(min(longest, len(tokens) - i), 0, -1):
            match = phrases.get(tuple(tokens[i:i + n]))
            if match:
                filters.add(*match)
                i += n
                break
        else:
            token = tokens[i]
            if token in STOPWORDS:
                pass
            elif token in COLOUR_WORDS:
                filters.add("attributes", token.title())
            elif token in vocabulary.terms:
                filters.add("keywords", token)
            elif singular(token) in vocabulary.terms:
                filters.add("keywords", singular(token))
            else:
                filters.add("ignored", token)
            i += 1
    return filters


def build_job_config(filters: Filters) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("currency", "STRING", CURRENCY),
        bigquery.ArrayQueryParameter("categories", "STRING", filters.categories),
        bigquery.ArrayQueryParameter("brands", "STRING", filters.brands),
        bigquery.ArrayQueryParameter("attributes", "STRING", filters.attributes),
        bigquery.ArrayQueryParameter("keywords", "STRING", filters.keywords),
        bigquery.ScalarQueryParameter("min_price", "FLOAT64", filters.min_price),
        bigquery.ScalarQueryParameter("min_inclusive", "BOOL", filters.min_inclusive),
        bigquery.ScalarQueryParameter("max_price", "FLOAT64", filters.max_price),
        bigquery.ScalarQueryParameter("max_inclusive", "BOOL", filters.max_inclusive),
    ])


def build_response(query: str, filters: Filters, rows: list[dict]) -> dict:
    """Split matches into in-stock results and hidden out-of-stock products, and write the message."""
    products = [
        {
            "product_id": r["product_id"],
            "name": r["name"],
            "brand": r["brand"],
            "category": r["category"],
            "attribute": r["attribute"],
            "price": float(r["price"]),
            "currency": r["currency"],
            "stock": int(r["stock"]),
        }
        for r in rows
    ]
    results = [p for p in products if p["stock"] > 0]
    hidden = [p for p in products if p["stock"] <= 0]

    if filters.is_empty():
        message = ("I could not find a category, brand, colour, price or product term in that request. "
                   "Try 'black handbag under AED 400'.")
    elif results:
        count = f"{len(results)} in-stock product{'s' if len(results) != 1 else ''}"
        message = f"Found {count} for {filters.describe()}."
    else:
        message = f"No in-stock products match {filters.describe()}."

    applied = asdict(filters)
    ignored = applied.pop("ignored")
    return {
        "query": query,
        "filters": applied,
        "filters_text": filters.describe(),
        "ignored_words": ignored,
        "message": message,
        "results": results,
        "hidden_out_of_stock": hidden,
    }


class ShoppingAssistant:
    """Answers natural-language queries from the BigQuery catalogue. Safe to share across threads."""

    def __init__(self, client: bigquery.Client | None = None, vocabulary_ttl: float = VOCABULARY_TTL_SECONDS):
        self._client = client
        self._vocabulary_ttl = vocabulary_ttl
        self._vocabulary: Vocabulary | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client()
        return self._client

    def vocabulary(self) -> Vocabulary:
        with self._lock:
            if self._vocabulary is None or time.monotonic() - self._loaded_at > self._vocabulary_ttl:
                rows = [dict(r) for r in self.client.query(VOCABULARY_SQL).result()]
                self._vocabulary = Vocabulary.from_rows(rows)
                self._loaded_at = time.monotonic()
            return self._vocabulary

    def ask(self, query: str) -> dict:
        query = query.strip()[:MAX_QUERY_LENGTH]
        filters = parse(query, self.vocabulary())
        rows = []
        if not filters.is_empty():
            job = self.client.query(SEARCH_SQL, job_config=build_job_config(filters))
            rows = [dict(r) for r in job.result()]
        return build_response(query, filters, rows)


def print_response(response: dict) -> None:
    print(f"\n> {response['query']}")
    if response["filters_text"]:
        print(f"  filters: {response['filters_text']}")
    if response["ignored_words"]:
        print(f"  ignored words: {', '.join(response['ignored_words'])}")
    print(f"  {response['message']}")
    for p in response["results"]:
        print(f"    {p['product_id']}  {p['name']:<22} {format_price(p['price'], p['currency']):>9}   {p['brand']}, stock {p['stock']}")
    for p in response["hidden_out_of_stock"]:
        print(f"  hidden, out of stock: {p['product_id']} {p['name']} ({format_price(p['price'], p['currency'])})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Natural-language product search over the BigQuery catalogue.")
    parser.add_argument("queries", nargs="*", default=DEMO_QUERIES, help="queries to run (default: demo set)")
    parser.add_argument("--json", action="store_true", help="print the raw JSON response")
    args = parser.parse_args()

    assistant = ShoppingAssistant()
    for query in args.queries:
        response = assistant.ask(query)
        if args.json:
            print(json.dumps(response, indent=2))
        else:
            print_response(response)


if __name__ == "__main__":
    main()
