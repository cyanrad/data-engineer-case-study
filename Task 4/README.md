# Task 4 - Recommendations

```sh
pip install -r requirements.txt
python recommend.py              # demo for U1, U2 and a new user (see recommend_output.txt)
python recommend.py U3 --k 5     # any customer key, top 5
```

## How it works
- It reads `retail_case.products_enriched` and `retail_case.event_items`
- Interactions build the customer's affinity to the category, brand and colour of the products they touched, weighted view = 1, add_to_cart = 3, purchase = 5.
- Popularity = views + 2 x purchased quantity.
- Candidate score = 2 x category affinity + brand affinity + colour affinity + 0.1 x popularity.
- Bounds: SKUs are in stock (`stock > 0`) and not already purchased by the customer.
- Each result returns SKU, score and a reason listing which attributes matched.

## Cold start
A customer with no interaction history (e.g. `NEW_USER`) gets the most popular SKUs, ranked by views + 2 x purchased quantity.

## Offline evaluation
Metric: `K` Hit Rate 
the share of customers for whom at least one of the top K recommendations is an item they later added to cart or purchased.

To avoid leakage, split by time rather than randomly.
Build affinities and popularity only from events before a cutoff timestamp, and evaluate only on events after it.