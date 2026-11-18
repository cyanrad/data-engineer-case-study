import argparse
from collections import Counter

from google.cloud import bigquery

DATASET = "retail_case"

EVENT_WEIGHTS = {"view_item": 1, "add_to_cart": 3, "purchase": 5}
FEATURE_WEIGHTS = {"category": 2, "brand": 1, "attribute": 1}
FEATURE_LABELS = {"category": "category", "brand": "brand", "attribute": "colour"}
POPULARITY_WEIGHT = 0.1


def load(client: bigquery.Client, sql: str) -> list[dict]:
    return [dict(row) for row in client.query(sql).result()]


def popularity(product: dict) -> int:
    return int(product["view_count"]) + 2 * int(product["purchased_quantity"])


def recommend(customer: str, products: list[dict], events: list[dict], k: int = 3) -> list[dict]:
    catalogue = {p["product_id"]: p for p in products}
    history = [e for e in events if e["user_id"] == customer and e["event_name"] in EVENT_WEIGHTS]
    purchased = {e["item_id"] for e in history if e["event_name"] == "purchase"}

    # Customer affinity per (feature, value), e.g. ("category", "Bags") -> 10
    affinity = Counter()
    for e in history:
        product = catalogue.get(e["item_id"])
        if product:
            for feature in FEATURE_WEIGHTS:
                affinity[(feature, product[feature])] += EVENT_WEIGHTS[e["event_name"]]

    results = []
    for p in products:
        if int(p["stock"]) <= 0 or p["product_id"] in purchased:
            continue
        matches = [f"{FEATURE_LABELS[feature]} {p[feature]}" for feature in FEATURE_WEIGHTS if affinity[(feature, p[feature])]]
        score = sum(w * affinity[(f, p[f])] for f, w in FEATURE_WEIGHTS.items())
        score += POPULARITY_WEIGHT * popularity(p)
        if not affinity:
            reason = f"cold start: popular item (views: {p['view_count']}, purchased: {p['purchased_quantity']})"
        elif matches:
            reason = "matches your history: " + ", ".join(matches)
        else:
            reason = "no history match, ranked by popularity"
        results.append({"sku": p["product_id"], "name": p["name"], "score": round(score, 2), "reason": reason})

    results.sort(key=lambda r: (-r["score"], r["sku"]))
    return results[:k]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("customers", nargs="*", default=["U1", "U2", "NEW_USER"])
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()

    client = bigquery.Client()
    products = load(client, f"SELECT * FROM {DATASET}.products_enriched")
    events = load(client, f"SELECT user_id, event_name, item_id FROM {DATASET}.event_items")
    for customer in args.customers:
        print(f"\n== {customer} ==")
        for r in recommend(customer, products, events, args.k):
            print(f"{r['sku']}  {r['score']:>6}  {r['name']:<22} {r['reason']}")


if __name__ == "__main__":
    main()
