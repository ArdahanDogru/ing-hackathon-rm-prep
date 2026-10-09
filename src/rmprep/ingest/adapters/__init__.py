"""Source adapters. Each adapter has two parts:

- fetch: get raw bytes (network or inbox), add them to a SnapshotWriter, and
  return a SourceRecord. Validates that the bytes parse before it stores them.
- parse: pure function from a finished Snapshot to DataPoints. Used by ingest
  and by replay; never touches the network, the clock or the current config.
"""
