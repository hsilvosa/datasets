# BNE Linked Data

## Dataset description

BNE Linked Data is a normalized Parquet release of the Linked Open Data dumps published by the Biblioteca Nacional de España. It represents bibliographic resources, authority records, subject headings, and the relationships among them as RDF statements.

The released snapshot contains 260,288,924 triples from official BNE files last modified on 6 September 2023. The files were preserved by Internet Archive on 20 September 2023. Each RDF statement is represented by one row; no relationships are inferred and no enrichment is added.

## Source and licence

- Publisher: [Biblioteca Nacional de España](https://datos.bne.es/)
- Documentation: [BNE Linked Data](https://www.bne.es/es/catalogos/datos-enlazados-bne/datos-enlazados)
- Snapshot date: 6 September 2023
- Licence: [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)

The live BNE download service returned HTTP 403 to automated requests when this release was built. The data files therefore come from preserved copies of the original BNE BZip2 responses in Internet Archive. Source URLs, dates, and transformations are recorded in `artifacts/provenance.json`.

## Configurations

| Configuration | Content | Rows | Parquet files | Parquet size |
|---|---|---:|---:|---:|
| `bibliographic` | Bibliographic resources, manifestations, works, and their relationships | 208,059,171 | 833 | 1,772,292,848 bytes |
| `authorities` | People, organisations, conferences, works, expressions, and other authority entities | 46,107,241 | 185 | 493,978,094 bytes |
| `subjects` | Subject headings and SKOS relationships | 6,122,512 | 25 | 51,987,039 bytes |

Each configuration has a single `train` split containing the complete graph collection. The source does not define a supervised prediction target or official train, validation, and test partitions.

## Fields

| Field | Description |
|---|---|
| `record_id` | Stable identifier formed from the collection and source-line number |
| `subject` | Subject IRI or blank-node identifier |
| `predicate` | Predicate IRI |
| `object` | Object IRI, blank-node identifier, or decoded literal value |
| `object_kind` | `iri`, `literal`, or `blank_node` |
| `language` | Language tag attached to a literal, when present |
| `datatype` | Datatype IRI attached to a literal, when present |
| `collection` | Source graph collection |
| `source_line` | One-based physical line number in the decompressed source |
| `snapshot_date` | Source snapshot date |

## Exploratory profile

The authority collection contains 5,624,909 distinct subjects and 96 predicates. The bibliographic collection contains 17,850,587 distinct subjects and 105 predicates. The subject collection contains 706,951 distinct subjects and 21 predicates.

Across all configurations there are 85,517,669 IRI objects and 174,771,255 literal objects. No blank-node objects occur. Subject data contains 1,604,451 language-tagged literals: 1,527,636 Spanish, 32,508 English, 20,530 French, 15,982 Catalan, 5,186 Basque, and 2,609 Galician.

Frequent relations include `rdf:type`, BNE identifiers and labels, bibliographic work and manifestation links, SKOS semantic relations, and 1,353,732 `owl:sameAs` authority links. Full counts and the thirty most frequent predicates per configuration are available in `artifacts/profile.json`.

## Processing and quality

The BZip2 sources were streamed, parsed as N-Triples, and written as Zstandard-compressed Parquet. The subjects source contains 865 external BnF IRIs split immediately before the closing `>` and continued on the next physical line. Those identifiable pairs were rejoined without altering their text; the first physical line remains in `source_line`.

All 260,288,924 normalized rows passed the graph-accounting and source-line checks. No source statements remain invalid. SHA-256 hashes for every Parquet shard are provided in `artifacts/checksums.json`. Additional machine-readable information is available in:

- `artifacts/normalization.json`
- `artifacts/profile.json`
- `artifacts/provenance.json`
- `artifacts/quality.json`
- `artifacts/schema.json`

## Intended uses and limitations

The data is suitable for graph analysis, bibliographic research, retrieval, entity linking, authority reconciliation, and recommendation research. Consumers should create task-specific and leakage-aware evaluation splits when needed.

The snapshot reflects the BNE catalogue as published in September 2023 and may contain cataloguing conventions, historical descriptions, or source errors. A relationship in the graph should not be interpreted as a current factual claim without checking the underlying catalogue record. The dataset contains metadata and identifiers, not digitized works or their full text.

## Attribution

When using the data, attribute the Biblioteca Nacional de España as the original publisher and retain the CC0 and provenance information supplied with the release.
