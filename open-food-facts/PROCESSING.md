# Processing

Stream the gzip JSONL dump one product at a time. Normalize stable identifiers, timestamps, names, brands, categories, ingredients, allergens, labels, countries, packaging, and nutrition values. Preserve irregular nested source fields in JSON columns. Write Parquet shards incrementally and do not produce an uncompressed JSONL copy.
