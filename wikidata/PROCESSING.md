# Processing

Stream the bzip2 dump line by line and remove only the surrounding JSON array punctuation. Emit entity metadata, multilingual text, sitelinks, claims, qualifiers, and references to bounded Parquet shards. Preserve datatypes and ranks. Never create an uncompressed copy of the full JSON dump.
