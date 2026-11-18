DROP TABLE IF EXISTS retail_case.products_enriched;
CREATE TABLE retail_case.products_enriched AS
WITH item_stats AS (
    SELECT  item_id,
            COUNTIF(event_name = 'view_item')                                                                           AS view_count,
            SUM(CASE WHEN event_name = 'purchase' THEN item_quantity ELSE 0 END)                                        AS purchased_quantity
      FROM  retail_case.event_items
     WHERE  event_name IN ('view_item', 'purchase')
     GROUP  BY 1
),
products AS (
    SELECT  *,
            ARRAY_TO_STRING([name, brand, category, attribute], ' ')                                                    AS combined
      FROM  retail_case.products_tmp
)
SELECT  p.product_id                                                                                                    AS product_id,
        p.name                                                                                                          AS name,
        p.brand                                                                                                         AS brand,
        p.category                                                                                                      AS category,
        p.price                                                                                                         AS price,
        p.currency                                                                                                      AS currency,
        p.stock                                                                                                         AS stock,
        p.attribute                                                                                                     AS attribute,
        CASE WHEN p.stock > 0 THEN 'in_stock' ELSE 'out_of_stock' END                                                   AS availability,
        -- unicode-normalised, lowercased, punctuation stripped, whitespace collapsed.
		-- Unclear what searchable text exactly means so assuming it means it's what the user would want to look up. Or some combination of the product's values
        TRIM(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(NORMALIZE(p.combined, NFKC)), r'[^\p{L}\p{N}]+', ' '), r'\s+', ' '))   AS search_text,
        COALESCE(s.view_count, 0)                                                                                       AS view_count,
        COALESCE(s.purchased_quantity, 0)                                                                               AS purchased_quantity,
        p.updated_at                                                                                                    AS updated_at
  FROM  products AS p
  LEFT  JOIN item_stats AS s ON  p.product_id = s.item_id
;