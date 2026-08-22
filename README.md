# Public Data Research Collection

This repository contains reproducible pipelines for collecting, normalizing, profiling, and publishing public-interest datasets. Each source lives in an independent directory and keeps its acquisition code, schemas, tests, and machine-readable analysis after the downloaded payload has been removed from local storage.

The project is intended exclusively for research, reproducibility, and public-interest data exploration. It does not provide medical, legal, financial, navigation, or operational advice. Every published dataset must retain the original source attribution, license or reuse terms, retrieval date, and provenance information. Source data remains the work and responsibility of its original publisher.

## What is published to Hugging Face

Each release contains normalized Parquet files, a dataset card, schema metadata, quality results, descriptive profiles, provenance, and checksums. Raw API responses, caches, credentials, and temporary downloads are not uploaded. Large tables are sharded so that a release can be produced and uploaded with less than approximately 50 GB of local working storage.

These are primarily observational and entity datasets rather than supervised-learning benchmarks. Unless a source defines a meaningful evaluation protocol, every configuration uses a single `train` split containing the complete table. Artificial train, validation, and test partitions would break temporal or relational context and imply a prediction task that the source does not define. Downstream researchers should construct task-specific, leakage-aware splits.

## Implemented Datasets

All datasets listed below have completed acquisition, schema validation, and Parquet normalization pipelines with verified row counts and compressed sizes.

| Order | Dataset | Description | Scale | Data size | Classes / Target Variables | Train / validation / test |
| ------: | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------: | -------------------------------------------: | ---------------------------------------------------- | ------------------------------------------------------------------ |
|     1 | [AEMPS CIMA](aemps-cima/) | Spanish medicines, active ingredients, presentations, regulatory status, documents, and relationships | 1,171,395 rows across 9 tables | 1.08 GB compressed Parquet | N/A; ATC hierarchical codes, administration routes, clinical statuses | 100% / 0% / 0% per table |
|     2 | [IGN Earthquakes](ign-earthquakes/) ([Hugging Face](https://huggingface.co/datasets/hsilvosa/ign-earthquakes)) | Verified seismic events in Spain and nearby areas with epicenters, depths, and magnitudes | 207,222 events | 5.41 MB compressed Parquet | N/A; continuous magnitudes (mb, mbLg, Mw) and coordinates | 100% / 0% / 0%; temporal splits downstream |
|     3 | [ENTSO-E Day-Ahead Prices and Load](entsoe-transparency/) ([Hugging Face](https://huggingface.co/datasets/hsilvosa/entsoe-day-ahead)) | European day-ahead electricity prices and actual system load by bidding zone | 13,353,368 rows across 2 tables | 552.67 MB compressed Parquet | N/A; continuous hourly price (EUR/MWh) and load (MW) | 100% / 0% / 0% per table; temporal splits downstream |
|     4 | [OpenPLACSP](openplacsp/) | Spanish public procurement notices, contract versions, lots, CPV classifications, and award records | 17,104,600 rows across 4 tables | 951.20 MB compressed Parquet | Contract statuses (`ADJ`, `RES`, `PUB`, `EV`, `PRE`, `ANUL`), CPV taxonomy | 100% / 0% / 0% per table; temporal splits downstream |
|     5 | [OMIE](omie-electricity/) | Iberian electricity wholesale market: full supply/demand bidding curves (`curva_pbc`) and hourly marginal prices | 17,148,748 rows across 2 tables | 211.23 MB compressed Parquet | Curve type (`Venta`, `Compra`), unit classification, clearing status (`Casada`, `No casada`) | 100% / 0% / 0% per market table |
|     6 | [BNE Linked Data](bne-linked-data/) ([Hugging Face](https://huggingface.co/datasets/hsilvosa/bne-linked-data)) | Authors, works, subjects, and bibliographic relationships from the National Library of Spain | 260,298,937 RDF triples across 3 graphs | 2.16 GiB compressed Parquet | N/A; entity-predicate-object knowledge triples | 100% / 0% / 0% per graph collection |
|     7 | [Spanish Cadastre](spanish-cadastre/) | Cadastral parcels, buildings, addresses, building units, zonings, and spatial geometries across Spain | 121,505,444 objects across 7 tables | 28.41 GB compressed Parquet | Cadastral use codes (residential, industrial, agricultural, commercial) | 100% / 0% / 0% in geographic shards |
|     8 | [Safecast Radiation](safecast/) | Worldwide geolocated ionizing radiation measurements (CPM, uSv/h) | 265,459,027 measurements | 15.93 GB compressed Parquet | N/A; continuous radiation counts (CPM, uSv/h) and coordinates | 100% / 0% / 0%; temporal splits downstream |
|     9 | [GDELT Events 1.0](gdelt-events/) | Global database of events, language, and tone (1979–2026 historical archive) | 889,592,605 events across 929 shards | 43.13 GB compressed Parquet | CAMEO Event codes, QuadClass (1: Verbal Coop, 2: Material Coop, 3: Verbal Conflict, 4: Material Conflict), Goldstein scale (-10 to +10) | 100% / 0% / 0% in temporal shards |
|    10 | [Wuxia Webnovel](wuxia-webnovel/) | Parallel Chinese-English literary corpus (GuoFeng sentence pairs + 6 curated full novels) | 1,918,602 translation rows across 2 configs | 225.86 MB compressed Parquet | Parallel text pairs (Chinese source -> English target) | Official corpus splits (train/val/test) + 100% chapters |
|    11 | [Congreso Debates & Voting](congreso-debates/) | Spanish Congress of Deputies: 41k verbatim speech transcripts (188M chars), 105k deputy votes, and initiatives (L1–L15) | 146,425 total records across 33 Parquet files | 51.02 MB compressed Parquet | Nominal vote stance (`Sí`, `No`, `Abstención`, `No vota`), initiative types | 100% / 0% / 0% per table; temporal splits downstream |

## Original Source Credits

All datasets are credited to their original publishing institutions and data communities:

| Dataset | Original publisher or data community |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| AEMPS CIMA | [Spanish Agency of Medicines and Medical Devices (AEMPS)](https://sede.aemps.gob.es/datos-abiertos/) |
| IGN Earthquakes | [Instituto Geográfico Nacional (IGN)](https://www.ign.es/web/sis-catalogo-terremotos) |
| ENTSO-E | [European Network of Transmission System Operators for Electricity](https://www.entsoe.eu/data/transparency-platform/) |
| OpenPLACSP | [Plataforma de Contratación del Sector Público](https://contrataciondelsectorpublico.gob.es/) |
| OMIE | [Operador del Mercado Ibérico de Energía](https://www.omie.es/) |
| BNE Linked Data | [Biblioteca Nacional de España](https://datos.bne.es/) |
| Spanish Cadastre | [Dirección General del Catastro](https://www.sedecatastro.gob.es/) |
| Safecast | [Safecast](https://safecast.org/) |
| GDELT Events | [GDELT Project](https://www.gdeltproject.org/) |
| Wuxia Webnovel | [GuoFeng Webnovel Corpus & WuxiaWorld Community](https://github.com/hsilvosa/datasets) |
| Congreso Debates & Votes | [Congreso de los Diputados de España (Datos Abiertos y Diarios de Sesiones)](https://www.congreso.es/datos-abiertos) |

## Repository Conventions

Every implemented dataset provides:

- resumable acquisition with explicit rate limiting and retries;
- immutable raw snapshots during a run and normalized Parquet outputs;
- `profile.json`, `schema.json`, `quality.json`, and `provenance.json` for automated audits;
- source attribution, reuse conditions, known limitations, and retrieval timestamps;
- deterministic processing and unit tests that do not require network access;
- a staging command that verifies exactly what will be uploaded before publication.

The repository does not redistribute data until its source-specific reuse conditions have been reviewed. Publication scripts require an explicit repository identifier and Hugging Face token.
