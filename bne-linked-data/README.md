# BNE Linked Data

**Published dataset:** [hsilvosa/bne-linked-data on Hugging Face](https://huggingface.co/datasets/hsilvosa/bne-linked-data)

This directory contains a reproducible pipeline for downloading, normalizing, profiling, and publishing the Linked Open Data dumps from the Biblioteca Nacional de España (BNE). The source represents bibliographic resources, authority records, and subject headings as an RDF knowledge graph.

The dataset is observational and relational. It has no target label, predefined classes, or official train, validation, and test split. Each collection is published as a `train` split so downstream users can build graph, retrieval, entity-linking, or recommendation tasks without an arbitrary split imposed upstream.

## Source and licence

- BNE Linked Data portal: <https://datos.bne.es/>
- Official documentation and downloads: <https://www.bne.es/es/catalogos/datos-enlazados-bne/datos-enlazados>
- Publisher: Biblioteca Nacional de España
- Data licence: [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)
- Released source snapshot: 6 September 2023, preserved by Internet Archive on 20 September 2023

The BNE documentation page describes an older 21 January 2021 extraction with more than four million bibliographic records, more than four million authority records, and approximately thirty million RDF triples. The reproducible release in this directory uses the later September 2023 official files preserved by Internet Archive. Direct source metadata identifies 6 September 2023 as the last-modified date for all three files.

As checked on 12 August 2026, the live BNE download URLs and SPARQL endpoint return HTTP 403 to automated requests from the current execution network because of a Cloudflare rule. `configs/default.json` therefore points to byte-for-byte captures of the official BZip2 responses in Internet Archive. Downloads remain resumable, and `configs/archive-2023.json` records the same immutable sources explicitly.

## Dataset contents

The release is designed around three Hugging Face configurations:

| Configuration | Source content | Compressed source | RDF triples | Parquet |
|---|---|---:|---:|---:|
| `bibliographic` | Bibliographic resources covering books, manuscripts, serials, maps, photographs, music, sound, and audiovisual material | 1,212,541,852 bytes | 208,059,171 | 1,772,292,848 bytes |
| `authorities` | People, organisations, conferences, works, expressions, geographic names, and other authority entities | 359,784,392 bytes | 46,107,241 | 493,978,094 bytes |
| `subjects` | Subject headings represented in SKOS | 33,805,185 bytes | 6,122,512 | 51,987,039 bytes |

Each RDF statement becomes one Parquet row. No triples are inferred, discarded, or enriched. The normalized columns are:

| Column | Meaning |
|---|---|
| `record_id` | Stable identifier formed from collection and decompressed source-line number |
| `subject` | Subject IRI or blank-node identifier |
| `predicate` | Predicate IRI |
| `object` | Object IRI, blank-node identifier, or decoded literal value |
| `object_kind` | `iri`, `literal`, or `blank_node` |
| `language` | Language tag attached to a literal, when present |
| `datatype` | Datatype IRI attached to a literal, when present |
| `collection` | Source collection name |
| `source_line` | One-based line number in the decompressed dump |
| `snapshot_date` | Date assigned by the source to the dump |

The statement representation preserves the complete graph while remaining easy to query with DuckDB, Polars, Spark, or Hugging Face Datasets. Subjects and objects can be joined directly to reconstruct authorship, subject, work, expression, manifestation, and external authority relationships.

## Capacity and duration

The verified download is 1,606,131,429 bytes (1.50 GiB) and took 10 minutes 46 seconds on the measured connection. Normalization took 1 hour 39 minutes, the full DuckDB profile took 49 seconds, and the resulting 1,043 Parquet shards occupy 2,318,257,981 bytes (2.16 GiB). Allow at least 10 GiB free when both processed data and a staging copy are retained. The pipeline streams BZip2 input and does not create a decompressed N-Triples copy.

## Exploratory profile

The September 2023 snapshot contains 260,288,924 triples. Authorities have 5,624,909 distinct subjects and 96 predicates; bibliographic data has 17,850,587 distinct subjects and 105 predicates; subjects have 706,951 distinct subjects and 21 predicates. Objects are split between 85,517,669 IRIs and 174,771,255 literals. No blank-node objects occur in the snapshot.

Subject labels contain 1,604,451 language-tagged literals: 1,527,636 Spanish, 32,508 English, 20,530 French, 15,982 Catalan, 5,186 Basque, and 2,609 Galician. Frequent relations include `rdf:type`, BNE identifiers and labels, bibliographic manifestation/work links, SKOS semantic relations, and 1,353,732 `owl:sameAs` authority links. Complete counts and the thirty most frequent predicates per collection are in `artifacts/profile.json`.

Run the estimate before every download:

```powershell
bne-pipeline estimate --config configs/default.json
```

## Installation

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Pipeline

Run each stage independently:

```powershell
bne-pipeline download --config configs/default.json
bne-pipeline normalize --config configs/default.json
bne-pipeline analyze --config configs/default.json
bne-pipeline stage --config configs/default.json
```

Or execute the complete workflow:

```powershell
bne-pipeline run --config configs/default.json
```

Interrupted downloads are retained as `.part` files and resumed with an HTTP range request when the server supports it. A file is promoted to the raw source path only after its byte size matches the length announced by the server. The sizes recorded in configuration are rounded planning estimates published by BNE.

If Cloudflare permits the files in a normal browser but blocks the pipeline, download them from the official documentation and place them at these exact paths:

```text
data/raw/autoridades.nt.bz2
data/raw/materias.nt.bz2
data/raw/bibliograficos.nt.bz2
```

Then start at `normalize`. Existing sources are checked for a non-empty BZip2 header, so an HTML block page cannot be mistaken for an RDF dump. Full BZip2 integrity and UTF-8/N-Triples validity are checked while the files are streamed during normalization.

The September 2023 subjects dump contains a small number of external BnF IRIs split immediately before the closing `>` and continued on the next physical line. The normalizer rejoins only this identifiable two-line pattern, preserves the first physical line in `source_line`, and reports the number of repaired statements. It does not apply general-purpose cleanup or alter IRI text.

## Small real-data validation

`configs/sample.json` uses the smallest archived official 2023 dump, subject headings, and stops normalization after 10,000 valid triples. Its purpose is to validate the real RDF structure without producing a complete release. The 33.8 MB BZip2 file still has to be downloaded in full because BZip2 cannot be decoded safely from an arbitrary byte range.

```powershell
bne-pipeline estimate --config configs/sample.json
bne-pipeline run --config configs/sample.json
```

The complete September 2023 snapshot uses `configs/default.json`; sample outputs are not mixed into a final release.

When the source returns HTTP 403, `configs/fixture.json` provides an offline integration check using five real `owl:sameAs` statements for the BNE authority record of Miguel de Cervantes (`XX1718747`). These links to DNB, VIAF, DBpedia, IdRef, and Libris are reproduced from the [MARiMbA project documentation](https://oeg.fi.upm.es/index.php/es/technologies/228-marimba/index.html) and the [BNE/OEG project presentation](https://datos.gob.es/sites/default/files/blog/file/01_2_introduccion_ii.pdf). The fixture proves the complete transformation and publication path, but it is not a replacement for either the 10,000-row sample or the full dump.

```powershell
bne-pipeline run --config configs/fixture.json
```

## Quality and provenance

The analysis stage writes the same publication artefacts used by the other projects in this repository:

- `artifacts/profile.json`: rows, distinct graph terms, object kinds, languages, and common predicates.
- `artifacts/normalization.json`: parsed, repaired, rejected, and output counts from normalization.
- `artifacts/schema.json`: physical schema and field semantics.
- `artifacts/quality.json`: non-empty tables, graph accounting, normalization row agreement, and invalid-line checks.
- `artifacts/provenance.json`: source, licence, snapshot, files, and transformations.
- `artifacts/checksums.json`: SHA-256 and size of every published Parquet shard.

Raw BZip2 dumps, partial downloads, local environments, and caches are excluded from Git and Hugging Face staging.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
```
