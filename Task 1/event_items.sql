DROP TABLE IF EXISTS retail_case.event_items;
CREATE TABLE retail_case.event_items AS 
SELECT  event_id,
        date_event,
        event_name,
        item.item_id                                                                                                    AS item_id,
        -- this keeps track of the offset
        item_offset,
        item.quantity                                                                                                   AS item_quantity,
        item.price                                                                                                      AS item_price,
        user_id,
        ga_session_id,
        page_url,
        market,
        time_event_local
  FROM  retail_case.events_clean, UNNEST(items) AS item WITH OFFSET AS item_offset
-- the items will CROSS JOIN that's on purpose. itemless events (e.g. E12/search) have no items, and there is no request to keep them for event_items