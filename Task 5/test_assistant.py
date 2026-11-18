"""Unit tests for the parser and response logic. No BigQuery access needed.

    python -m unittest -v test_assistant.py
"""

import unittest

from assistant import Vocabulary, build_response, normalize, parse, singular

# Same rows as retail_case.products_enriched after the Task 3 update.
CATALOGUE = [
    ("P001", "Black leather handbag", "Brand A", "Bags", 450, 8, "Black"),
    ("P002", "Black mini handbag", "Brand B", "Bags", 320, 4, "Black"),
    ("P003", "Amber eau de parfum", "Tom Ford", "Fragrance", 480, 10, "Amber"),
    ("P004", "Rose eau de parfum", "Brand C", "Fragrance", 290, 6, "Rose"),
    ("P005", "Leather tote", "Brand A", "Bags", 650, 0, "Brown"),
    ("P006", "Citrus perfume", "Brand D", "Fragrance", 180, 12, "Citrus"),
    ("P007", "Silk scarf", "Brand E", "Accessories", 150, 9, "Blue"),
    ("P008", "Black shoulder bag", "Brand B", "Bags", 350, 0, "Black"),
    ("P009", "Black crossbody bag", "Brand E", "Bags", 280, 6, "Black"),
]
ROWS = [
    {
        "product_id": pid, "name": name, "brand": brand, "category": category, "price": price,
        "stock": stock, "attribute": attribute, "currency": "AED",
        "search_text": normalize(f"{name} {brand} {category} {attribute}"),
    }
    for pid, name, brand, category, price, stock, attribute in CATALOGUE
]
VOCAB = Vocabulary.from_rows(ROWS)


def run_in_memory(query: str) -> dict:
    """Mirror of SEARCH_SQL in Python, so the end-to-end behaviour can be tested offline."""
    f = parse(query, VOCAB)
    rows = []
    if not f.is_empty():
        for r in ROWS:
            if f.categories and r["category"] not in f.categories:
                continue
            if f.brands and r["brand"] not in f.brands:
                continue
            if f.attributes and r["attribute"] not in f.attributes:
                continue
            if f.min_price is not None and not (r["price"] > f.min_price or (f.min_inclusive and r["price"] == f.min_price)):
                continue
            if f.max_price is not None and not (r["price"] < f.max_price or (f.max_inclusive and r["price"] == f.max_price)):
                continue
            if any(k not in r["search_text"].split() for k in f.keywords):
                continue
            rows.append(r)
    rows.sort(key=lambda r: (r["price"], r["product_id"]))
    return build_response(query, f, rows)


def ids(products: list[dict]) -> list[str]:
    return [p["product_id"] for p in products]


class ParseTest(unittest.TestCase):
    def test_category_colour_price(self):
        f = parse("black handbag under AED 400", VOCAB)
        self.assertEqual(f.categories, ["Bags"])
        self.assertEqual(f.attributes, ["Black"])
        self.assertEqual((f.max_price, f.max_inclusive), (400, False))
        self.assertEqual(f.keywords, [])

    def test_multi_word_brand(self):
        f = parse("Tom Ford fragrance under AED 500", VOCAB)
        self.assertEqual(f.brands, ["Tom Ford"])
        self.assertEqual(f.categories, ["Fragrance"])
        self.assertEqual(f.max_price, 500)

    def test_brand_with_single_letter(self):
        self.assertEqual(parse("brand a bags", VOCAB).brands, ["Brand A"])

    def test_price_phrases(self):
        cases = {
            "bag under 400": (None, 400, False),
            "bag below aed400": (None, 400, False),
            "bag up to 400 dhs": (None, 400, True),
            "bag over AED 300": (300, None, None),
            "bag at least 300": (300, None, None),
            "bag between 200 and 300": (200, 300, True),
            "bag from AED 300 to AED 200": (200, 300, True),
            "bag 200-300": (200, 300, True),
            "bag under AED 1,200.50": (None, 1200.5, False),
        }
        for query, (low, high, high_inclusive) in cases.items():
            with self.subTest(query=query):
                f = parse(query, VOCAB)
                self.assertEqual(f.min_price, low)
                self.assertEqual(f.max_price, high)
                if high is not None:
                    self.assertEqual(f.max_inclusive, high_inclusive)
                self.assertEqual(f.categories, ["Bags"])
                self.assertEqual(f.ignored, [])

    def test_tightest_bound_wins(self):
        f = parse("bag under 500 and below 300", VOCAB)
        self.assertEqual(f.max_price, 300)

    def test_free_text_term_and_plural(self):
        f = parse("silk scarves", VOCAB)
        self.assertEqual(f.keywords, ["silk", "scarf"])

    def test_unknown_colour_is_still_a_filter(self):
        self.assertEqual(parse("red handbag", VOCAB).attributes, ["Red"])

    def test_unknown_words_are_reported(self):
        f = parse("show me a sparkly bag please", VOCAB)
        self.assertEqual(f.categories, ["Bags"])
        self.assertEqual(f.ignored, ["sparkly"])

    def test_no_filters(self):
        self.assertTrue(parse("hello there", VOCAB).is_empty())
        self.assertTrue(parse("", VOCAB).is_empty())


class EndToEndTest(unittest.TestCase):
    def test_black_handbag_under_400_hides_out_of_stock(self):
        r = run_in_memory("black handbag under AED 400")
        self.assertEqual(ids(r["results"]), ["P009", "P002"])
        self.assertEqual(ids(r["hidden_out_of_stock"]), ["P008"])
        self.assertEqual([p["price"] for p in r["results"]], [280.0, 320.0])

    def test_tom_ford_fragrance_under_500(self):
        r = run_in_memory("Tom Ford fragrance under AED 500")
        self.assertEqual(ids(r["results"]), ["P003"])

    def test_no_results(self):
        r = run_in_memory("black handbag under AED 100")
        self.assertEqual(r["results"], [])
        self.assertTrue(r["message"].startswith("No in-stock products match"))

    def test_updated_catalogue_values(self):
        # P001's negative-price update is rejected (450 kept), P008 updated to 350 and out of stock.
        r = run_in_memory("black leather handbag")
        self.assertEqual([(p["product_id"], p["price"]) for p in r["results"]], [("P001", 450.0)])

    def test_never_returns_out_of_stock(self):
        r = run_in_memory("bags")
        self.assertTrue(all(p["stock"] > 0 for p in r["results"]))
        self.assertEqual(ids(r["hidden_out_of_stock"]), ["P008", "P005"])

    def test_empty_query_message(self):
        r = run_in_memory("hello")
        self.assertEqual(r["results"], [])
        self.assertIn("could not find", r["message"])


class HelpersTest(unittest.TestCase):
    def test_singular(self):
        self.assertEqual(singular("bags"), "bag")
        self.assertEqual(singular("accessories"), "accessory")
        self.assertEqual(singular("scarves"), "scarf")
        self.assertEqual(singular("boxes"), "box")
        self.assertEqual(singular("glass"), "glass")

    def test_normalize_matches_search_text(self):
        self.assertEqual(normalize("  Tom-Ford  EAU de Parfum! "), "tom ford eau de parfum")


if __name__ == "__main__":
    unittest.main()
