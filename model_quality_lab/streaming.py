"""Optional Kafka transport and ClickHouse event sink. Offsets follow durability."""
from __future__ import annotations
import base64
import json
import os
import time
import urllib.request
from pathlib import Path
from pydantic import TypeAdapter
from .schema import Event
from .store import Store
from .telemetry import configure, tracer


def publish(envelope: dict, topic: str = "mql.events") -> None:
    from confluent_kafka import Producer
    producer = Producer({"bootstrap.servers": os.environ["MQL_KAFKA_BROKERS"],
                         "enable.idempotence": True, "acks": "all", "message.timeout.ms": 10000})
    errors = []
    producer.produce(topic, key=envelope.get("request_id", "invalid"), value=json.dumps(envelope),
                     on_delivery=lambda error, message: errors.append(error) if error else None)
    remaining = producer.flush(12)
    if remaining or errors:
        raise RuntimeError("Broker did not acknowledge event; retry the same event ID")


class ClickHouseSink:
    def __init__(self):
        self.url = os.environ.get("MQL_CLICKHOUSE_URL", "http://localhost:8123")
        self.auth = base64.b64encode((os.environ.get("MQL_CLICKHOUSE_USER", "mql") + ":" + os.environ.get("MQL_CLICKHOUSE_PASSWORD", "local-lab")).encode()).decode()

    def execute(self, query: str) -> str:
        request = urllib.request.Request(self.url, query.encode(), {"Authorization": "Basic " + self.auth})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode()

    def initialize(self):
        self.execute("CREATE TABLE IF NOT EXISTS mql_events (event_id String, request_id String, kind LowCardinality(String), model LowCardinality(String), payload String, version UInt64) ENGINE=ReplacingMergeTree(version) ORDER BY event_id")

    def write(self, envelope: dict):
        row = {"event_id": envelope["event_id"], "request_id": envelope["request_id"], "kind": envelope["kind"],
               "model": envelope["body"].get("model", "outcome"), "payload": json.dumps(envelope["body"]),
               "version": time.time_ns()}
        self.execute("INSERT INTO mql_events FORMAT JSONEachRow\n" + json.dumps(row))


def consume():
    from confluent_kafka import Consumer
    runtime=Path(os.environ.get("MQL_RUNTIME", ".runtime"));configure(runtime)
    store=Store(runtime/'lab.sqlite3')
    sink=ClickHouseSink();sink.initialize()
    consumer=Consumer({"bootstrap.servers":os.environ["MQL_KAFKA_BROKERS"],"group.id":"mql-projection-v1",
                       "auto.offset.reset":"earliest","enable.auto.commit":False})
    consumer.subscribe(['mql.events'])
    try:
        while True:
            message=consumer.poll(1)
            if message is None:continue
            if message.error():raise RuntimeError(str(message.error()))
            try:
                envelope=TypeAdapter(Event).validate_json(message.value()).model_dump()
            except ValueError:
                # Invalid raw input is not copied to a dead-letter payload or logs.
                publish({'request_id':'invalid','reason':'schema rejected','partition':message.partition(),'offset':message.offset()},'mql.deadletter')
                consumer.commit(message=message,asynchronous=False);continue
            try:
                with tracer().start_as_current_span('kafka.project'):
                    try:
                        store.accept(envelope['event_id'],envelope['kind'],envelope['request_id'],envelope['body'])
                    except ValueError:
                        store.audit('kafka.identity_conflict',{'event_id':envelope['event_id']})
                        publish({'request_id':'invalid','reason':'identity conflict','partition':message.partition(),'offset':message.offset()},'mql.deadletter')
                        consumer.commit(message=message,asynchronous=False);continue
                    store.drain_batch()
                    # The sink may be redelivered after a crash. FINAL deduplicates event identities.
                    sink.write(envelope)
                    consumer.commit(message=message,asynchronous=False)
            except Exception:
                # Do not advance the offset after a partial failure; restart and replay it.
                raise
    finally:consumer.close()

if __name__=='__main__':consume()
