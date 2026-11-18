-- Query to get view and purchase count.
-- In a real analytical query it's better of course to use item_name instead of id but that right now requres a join on product
-- product cleaning and table is a task for later according to the shared document.
SELECT  item_id,
        COUNTIF(event_name = 'view_item')                                         AS view_count,
        SUM(CASE WHEN event_name = 'purchase' THEN item_quantity ELSE 0 END)     AS purchased_quantity
  FROM  retail_case.event_items
 WHERE  event_name IN ('view_item', 'purchase')
 GROUP  BY 1
 ORDER  BY 1
;