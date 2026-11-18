-- Creating tmp table for reproducability
DROP TABLE IF EXISTS retail_case.products_tmp;
CREATE TABLE retail_case.products_tmp AS SELECT * FROM retail_case.products_raw;

-- in-place merging. Would be applied on products_raw.
MERGE retail_case.products_tmp AS t
USING (
    SELECT  *
      FROM  retail_case.products_inc
     WHERE  price >= 0 -- rejecting rows with negative price
            AND stock >= 0 -- rejecting rows with negative stock
    -- taking the newest row for a product. Not very useful in our case but important in a real scenario & requested in document.
    QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY updated_at DESC) = 1
) AS inc ON t.product_id = inc.product_id

  WHEN  MATCHED 
        AND inc.updated_at > t.updated_at THEN -- updating only when we have a newer version.
UPDATE  SET name = inc.name,
            brand = inc.brand,
            category = inc.category,
            price = inc.price,
            stock = inc.stock,
            attribute = inc.attribute,
            currency = inc.currency,
            updated_at = inc.updated_at

  WHEN   NOT MATCHED THEN INSERT ROW
;

SELECT *  FROM  retail_case.products_tmp;

-- validating that there are no negative values.
SELECT product_id FROM retail_case.products_tmp WHERE price < 0 OR stock < 0;