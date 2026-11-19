# AI Usage
## General Usage
Used primarily Claude Code for this exercise
1. Looking up specific syntax for google big query & python pub/sub for platform specific work. Example
	- "How to create a pubsub topic using gcloud CLI"
	- "How to query nested objects in GCP BQ"
	- "Is there a simpler way to implement python pubsub consumers"
2. Reviewes for hand written code. All SQL queries are hand wirtten. Reviewed by AI to make sure no edge case was missed, using a blanket prompt like "review the requirements of Task 1 and the SQL I wrote for it and inform me if there is any issues or requirements I missed.
3. Python & Readmes are mostly AI generated and fully reviewed. Used more specific prompts such as "Create the publisher function and add comments on each line so I can review your logic" Once generated I'd review the logic, make sure it's sound. Test out the script and remove/improve parts that were either over engineered or redundant. 

## Exact Usage
### Planning and setup
1. Summarise the brief as a checklist per task and suggest where to start.
2. Split the 6-hour timebox across tasks, weighted by points, and update the plan as tasks finish.
3. Recommend the best way to load the data into BigQuery.

### Task 1 - GA4 ingestion and nested SQL
4. Compare ways to extract nested GA4 fields (correlated `UNNEST` subquery vs `UNNEST` join).
5. Review my daily/intraday reconciliation approach.
6. Review my `events_clean` and `event_items` queries and their output against the requirements.
7. Review my views and purchases per product query.
8. Explain what partitioning means in the context of this task. Does it refer to table partitioning at the storage level, or to another BigQuery concept?

### Task 2 - Streaming to BigQuery
9. Give me the commands to create the pubsub channels, both the main one and the dead-letter one. If repeats and failures can be handled by default, add that to the configuration.
10. Explain the Pub/Sub channel settings you chose, such as the dead-letter topic and ack deadline, and point out any edge cases for these configurations.
11. How are messages published and consumed with GCP pubsub in Python?
12. Generate the channel subscription commands and the required roles.
13. Create the publisher function and comment each line so I can review your logic. Don't implement a local mode, since I have access to the actual GCP pubsub.
14. Create the consumer function and comment each line so I can review your logic.
15. Split up the consumer function: use a class to hold the GCP connections, add a separate function for each piece of GCP functionality, and finish with one simple function that simulates message consumption and delays.
16. Check that dead-letter recording and event-time handling are working, and fix the step order.

### Task 3 - Product feed
17. Explain what "apply the updates incrementally" means in this case.
18. Explain what is meant by `search_text` and add the normalisation logic to the query.
19. Validate the `products_enriched` query and check whether I missed any requirements.

### Task 4 - Recommendations
20. Build a simple Python recommendation function that reads from BigQuery. Add comments and explain your decisions.
21. Why did you choose these specific constants?
22. Explain offline evaluation metrics (hit rate@K) and how to avoid training/evaluation leakage.

### Task 5 - Shopping assistant
23. Build the shopping assistant with a small web interface, reading the catalogue from BigQuery.

### Documentation and packaging
24. Write READMEs for each task and a short top-level README with a screenshot, keeping them concise.

# Task 6
Unfortunately didn't have the time to complete task 6 within the given timeline. As it requires GCP specific experience, where most of my experience lies with AWS.
