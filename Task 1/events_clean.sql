DROP TABLE IF EXISTS retail_case.events_clean;
CREATE TABLE retail_case.events_clean AS 
WITH baseset AS (
    SELECT  *
      FROM  (
              SELECT  *, -- generally better to write out every column, but keeping it in this case * for simplicity.
                     -- Adding arbitrary source priority, the overlapping data between the two systems match exactly,
                     -- but the data from the intraday seems to be newer so prioratizing that
                     1                                                                                                  AS source_priority
               FROM  retail_case.events_daily
              UNION  ALL
             SELECT  *,
                     2                                                                                                  AS source_priority
               FROM  retail_case.events_intraday
            )
            -- It's best to use a window function. Using qualify so we don't have to have another query to filter for the rank.
            -- Notes:
            --   1. If we know for a fact that the events will exactly match each other based on event_id (or some other equivalent field)
            --      then we can easily do GROUP BY ALL though it's not very reliable as a change in one of the other column will cause duplicates
            --   2. If one system should be prioratized over the other we should put source_priority before timestamp
    QUALIFY (ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp DESC, source_priority DESC) = 1)
)
SELECT  event_id                                                                                                        AS event_id,
        DATE(TIMESTAMP_MICROS(event_timestamp), 'Asia/Dubai')                                                           AS date_event,
        event_name                                                                                                      AS event_name,
        -- I'm aware the anon at the end will not be triggered in this case, but in a real system where changes can be made
        -- the GA might one day change and they might stop prividing the anon and in this case we will be dealing with 
        COALESCE(user_id, user_pseudo_id, 'anon')                                                                       AS user_id,
        (SELECT value.int_value    FROM UNNEST(event_params)    WHERE key = 'ga_session_id')                            AS ga_session_id,
        (SELECT value.string_value FROM UNNEST(event_params)    WHERE key = 'page_location')                            AS page_url,
        (SELECT value.string_value FROM UNNEST(user_properties) WHERE key = 'market')                                   AS market,
        ARRAY_LENGTH(items)                                                                                             AS item_count,
        items                                                                                                           AS items,
        DATETIME(TIMESTAMP_MICROS(event_timestamp), 'Asia/Dubai')                                                       AS time_event_local
  FROM  baseset
;