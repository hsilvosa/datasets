# Public Data Research Collection

This repository contains reproducible pipelines for collecting, normalizing, profiling, and publishing public-interest datasets. Each source lives in an independent directory and keeps its acquisition code, schemas, tests, and machine-readable analysis after the downloaded payload has been removed from local storage.

The project is intended exclusively for research, reproducibility, and public-interest data exploration. It does not provide medical, legal, financial, navigation, or operational advice. Every published dataset must retain the original source attribution, license or reuse terms, retrieval date, and provenance information. Source data remains the work and responsibility of its original publisher.

## What is published to Hugging Face

Each release contains normalized Parquet files, a dataset card, schema metadata, quality results, descriptive profiles, provenance, and checksums. Raw API responses, caches, credentials, and temporary downloads are not uploaded. Large tables are sharded so that a release can be produced and uploaded with less than approximately 50 GB of local working storage.

These are primarily observational and entity datasets rather than supervised-learning benchmarks. Unless a source defines a meaningful evaluation protocol, every configuration uses a single `train` split containing the complete table. Artificial train, validation, and test partitions would break temporal or relational context and imply a prediction task that the source does not define. Downstream researchers should construct task-specific, leakage-aware splits.

## Dataset roadmap

Implemented datasets show verified row counts and compressed Parquet sizes from their published snapshots. Datasets not yet implemented retain planning estimates, not guarantees. “Classes” means an explicit supervised target taxonomy; `N/A` indicates that the source is not a classification dataset. The order is the saved implementation priority.

| Order | Dataset | Description | Scale | Data size | Classes | Train / validation / test |
|---:|---|---|---:|---:|---|---|
| 1 | [AEMPS CIMA](aemps-cima/) | Spanish medicines, active ingredients, presentations, regulatory status, documents, and relationships | 1,171,395 rows across 9 tables | 1.08 GB compressed Parquet | N/A; categorical fields are documented, not labels | 100% / 0% / 0% per table |
| 2 | [IGN Earthquakes](ign-earthquakes/) ([Hugging Face](https://huggingface.co/datasets/hsilvosa/ign-earthquakes)) | Verified seismic events in Spain and nearby areas | 207,222 events | 5.41 MB compressed Parquet | N/A | 100% / 0% / 0%; temporal splits downstream |
| 3 | Meteocat XEMA | Half-hourly observations from Catalan automatic weather stations | 10M–100M observations | 5–50 GB | N/A | 100% / 0% / 0%; temporal splits downstream |
| 4 | SiAR | Spanish agroclimatic station observations | 10M–100M+ observations | 5–50 GB | N/A | 100% / 0% / 0%; temporal splits downstream |
| 5 | REE e·sios | Electricity demand, generation, prices, and system indicators | 10M–100M values | 5–100 GB | N/A | 100% / 0% / 0% per indicator family |
| 6 | OpenPLACSP | Spanish public procurement notices and awards | 1M–10M records | 10–100+ GB without PDFs | N/A | 100% / 0% / 0%; temporal splits downstream |
| 7 | OMIE | Iberian electricity market results, offers, and curves | 10M–100M rows | 10–100 GB | N/A | 100% / 0% / 0% per market table |
| 8 | SOCIB | Oceanographic sensors, gliders, and coastal radar observations | 10M–1B+ measurements | 100 GB–several TB | N/A | 100% / 0% / 0% per source collection |
| 9 | BNE Linked Data | Authors, works, subjects, and bibliographic relationships | Millions of entities | 10–100 GB | N/A | 100% / 0% / 0% per entity/edge table |
| 10 | Spanish Cadastre | Parcels, buildings, uses, and geometries | 10M–100M objects | 50–500+ GB | N/A | 100% / 0% / 0% in geographic shards |
| 11 | Historical Press | Newspaper OCR, metadata, and scanned pages | 1M–10M+ pages | Tens of GB for text; 1–20+ TB with images | N/A | 100% / 0% / 0% per collection/time shard |
| 12 | Meteoclimatic | Observations from privately operated weather stations | Millions–100M+ points | 1–50 GB | N/A | 100% / 0% / 0%; subject to reuse review |
| 13 | Reverse Beacon Network | Worldwide amateur-radio signal reception reports | 100M–1B+ spots | 20–300+ GB | N/A | 100% / 0% / 0% in temporal shards |
| 14 | Safecast | Geolocated radiation measurements | More than 150M measurements | 10–50+ GB | N/A | 100% / 0% / 0%; temporal splits downstream |
| 15 | RIPE Atlas | Ping, traceroute, DNS, and network measurements | 1B–100B+ results | TB–tens of TB | N/A | 100% / 0% / 0% per measurement config |
| 16 | EMSC / LastQuake | Earthquakes and crowdsourced felt reports | 1M–10M events/reports | 1–50 GB | N/A unless a derived intensity task is defined | 100% / 0% / 0%; reuse terms require review |
| 17 | CHILDES / TalkBank | Child and family speech transcripts and media | Hundreds–thousands of sessions | Under 10 GB text; 10 GB–TB media | Corpus-dependent | Preserve official ratios where present; otherwise 100% / 0% / 0% |
| 18 | Observation.org | Species observations, locations, labels, and media references | More than 100M observations | 10–100 GB metadata; several TB media | Taxonomy-dependent | Preserve source ratios; licensing per record/media |
| 19 | Movebank | Animal GPS trajectories and study metadata | 1k–10M points per study | 10 GB–TB aggregate | N/A | 100% / 0% / 0% per study; permissions vary |
| 20 | Global Fishing Watch | Vessel positions and inferred activity events | Billions of points | TB scale | Event categories are product-dependent | 100% / 0% / 0% per product/time config |

## Original source credits

The planned collections are credited to their original publishers below. Inclusion in the roadmap does not imply that redistribution has already been approved; reuse conditions are reviewed again when each pipeline is implemented.

| Dataset | Original publisher or data community |
|---|---|
| AEMPS CIMA | [Spanish Agency of Medicines and Medical Devices (AEMPS)](https://sede.aemps.gob.es/datos-abiertos/) |
| IGN Earthquakes | [Instituto Geográfico Nacional (IGN)](https://www.ign.es/web/sis-catalogo-terremotos) |
| Meteocat XEMA | [Servei Meteorològic de Catalunya](https://www.meteo.cat/) |
| SiAR | [Spanish Ministry of Agriculture, Fisheries and Food](https://eportal.mapa.gob.es/websiar/) |
| REE e·sios | [Red Eléctrica de España](https://www.esios.ree.es/) |
| OpenPLACSP | [Plataforma de Contratación del Sector Público](https://contrataciondelsectorpublico.gob.es/) |
| OMIE | [Operador del Mercado Ibérico de Energía](https://www.omie.es/) |
| SOCIB | [Balearic Islands Coastal Observing and Forecasting System](https://www.socib.es/) |
| BNE Linked Data | [Biblioteca Nacional de España](https://datos.bne.es/) |
| Spanish Cadastre | [Dirección General del Catastro](https://www.sedecatastro.gob.es/) |
| Historical Press | [Biblioteca Virtual de Prensa Histórica, Spanish Ministry of Culture](https://prensahistorica.mcu.es/) |
| Meteoclimatic | [Meteoclimatic community](https://www.meteoclimatic.net/) |
| Reverse Beacon Network | [Reverse Beacon Network](https://www.reversebeacon.net/) |
| Safecast | [Safecast](https://safecast.org/) |
| RIPE Atlas | [RIPE NCC](https://atlas.ripe.net/) |
| EMSC / LastQuake | [European-Mediterranean Seismological Centre](https://www.emsc-csem.org/) |
| CHILDES / TalkBank | [TalkBank and contributing researchers](https://childes.talkbank.org/) |
| Observation.org | [Observation International and its contributors](https://observation.org/) |
| Movebank | [Movebank, the Max Planck Institute of Animal Behavior, and contributing studies](https://www.movebank.org/) |
| Global Fishing Watch | [Global Fishing Watch](https://globalfishingwatch.org/datasets-and-code/) |

## Repository conventions

Every implemented dataset should provide:

- resumable acquisition with explicit rate limiting and retries;
- immutable raw snapshots during a run and normalized Parquet outputs;
- `profile.json`, `schema.json`, `quality.json`, and `provenance.json` for web applications and automated audits;
- source attribution, reuse conditions, known limitations, and retrieval timestamps;
- deterministic processing and tests that do not require network access;
- a staging command that shows exactly what will be uploaded before publication.

The repository does not redistribute data until its source-specific reuse conditions have been reviewed. Publication scripts require an explicit repository identifier and Hugging Face token.
