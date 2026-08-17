# Processing

Use a history-aware libosmium reader against the PBF itself. Emit separate Parquet tables for object versions, tags, way node references, and relation members. Partition by object type and a stable identifier bucket. Never convert the planet file to XML and never load all objects into memory.
