# send each line of data/stream_events.jsonl as one Pub/Sub message.

from pathlib import Path
from common import DATA_DIR, PROJECT, TOPIC
from google.cloud import pubsub_v1

def publish(source: Path = DATA_DIR / "stream_events.jsonl") -> int:
    lines = [line for line in source.read_bytes().splitlines() if line.strip()]
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT, TOPIC)
    futures = [publisher.publish(topic_path, line) for line in lines]
    for future in futures:
        future.result()  # raises if a publish still failed after the client's built-in retries
    return len(lines)


if __name__ == "__main__":
    print(f"published {publish()} messages")
