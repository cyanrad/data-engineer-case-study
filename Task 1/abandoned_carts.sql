WITH base AS (
    SELECT  item_id,
            user_id,
            event_name,
            item_quantity,
            time_event_local,
            -- The latest purchase of each product for each customer.
            -- We remove any cases where an item is added to cart after the purchase or where the purchase time is null.
            -- This handles cases where the user does add_to_cart -> purchase -> add_to_cart again for the same product.
            MAX(CASE WHEN event_name = 'purchase' THEN time_event_local END) OVER (PARTITION BY user_id, item_id)       AS time_last_purchase
      FROM  retail_case.event_items
     WHERE  event_name IN ('add_to_cart', 'purchase')
     -- In this case it's simple since there doesn't seem to be "removed_from_cart" event
     -- and there isn't really a time window. But I imagine in a real scenario we would want to consider users
     -- who for example added an item and didn't buy it within some given amount of time. Or ones who stopped using the platform, etc.
     -- I'm also not handling cases where there are multiple add_to_cart (e.g. 2 of the item added) but only 1 is purchased since there is
     -- no exact requirement for handling that.
)
SELECT  user_id                                                                                                         AS user_id,
        item_id                                                                                                         AS item_id,
        COUNT(*)                                                                                                        AS abandoned_add_to_cart_count
  FROM  base
 WHERE  event_name = 'add_to_cart'
   AND  (time_last_purchase IS NULL OR time_event_local > time_last_purchase)
        -- Excluding the anon user_id as it may belong to many different people so we can't accurately track who abandoned their cart.
        -- In a real scenario we might choose to track this person based on things like session, device id, ip, etc...
   AND  user_id != 'anon'
 GROUP  BY 1,2
 ORDER  BY 1,2
;
