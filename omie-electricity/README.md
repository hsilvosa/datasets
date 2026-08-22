---
license: other
language:
- es
- pt
- en
pretty_name: "OMIE Iberian Electricity Market Bidding Curves and Marginal Prices"
task_categories:
- time-series-forecasting
- tabular-regression
- reinforcement-learning
tags:
- energy
- electricity
- reinforcement-learning
- time-series
- bidding-curves
- market-clearing
- spain
- portugal
- omie
- public-data
size_categories:
- 10M<n<100M
configs:
- config_name: bidding_curves
  data_files:
  - split: train
    path: data/omie_bidding_curves_*.parquet
- config_name: marginal_prices
  data_files:
  - split: train
    path: data/omie_hourly_marginal_price.parquet
---

# OMIE: Iberian Wholesale Electricity Market (Spain and Portugal)

Standardized dataset containing over **17.15 million rows** of market-clearing data from the Iberian wholesale electricity market, operated by **OMIE (Operador del Mercado Ibérico de Energía)**.

It includes full aggregate **supply and demand bidding curves block-by-block (`curva_pbc`)** and the continuous time series of **hourly marginal prices and cleared energy volumes**.

---

## Dataset Summary

| Configuration | Rows | Temporal Coverage | Description | Parquet Size |
| :--- | :--- | :--- | :--- | :--- |
| **`bidding_curves`** | **17,093,765 rows** | Full Year 2024 | Full supply (sale) and demand (purchase) matched and unmatched bidding steps per hour | **210 MB** |
| **`marginal_prices`** | **54,983 rows** | 2023–2026 (Hourly) | Hourly marginal prices (EUR/MWh) and cleared energy (MWh) for Spain and Portugal | **880 KB** |

---

## Data Structure and Schema

### 1. `bidding_curves` (`omie_bidding_curves_2024.parquet`)
Discrete bid steps submitted by market participants (generators, retailers, and consumers):

| Field | Type | Description |
| :--- | :--- | :--- |
| `date` | `string` | Market delivery date (`YYYY-MM-DD`). |
| `hour` | `int32` | Hour of the day (1 to 24/25). |
| `curve_type` | `string` | Type of curve (`Venta` for supply / `Compra` for demand). |
| `unit_type` | `string` | Unit classification (`Nacional`, `Importación`, `Exportación`). |
| `energy_mwh` | `float64` | Energy volume bid in this discrete step (MWh). |
| `price_eur_mwh` | `float64` | Bid price (EUR/MWh). |
| `cleared_status` | `string` | Clearing result for this bid step (`Casada` for cleared / `No casada` for unmatched). |

### 2. `marginal_prices` (`omie_hourly_marginal_price.parquet`)
Continuous hourly time series resulting from the Day-Ahead market clearing algorithm:

| Field | Type | Description |
| :--- | :--- | :--- |
| `date` | `string` | Delivery date (`YYYY-MM-DD`). |
| `hour` | `int32` | Hour of the day (1 to 24). |
| `price_spain_eur_mwh` | `float64` | Hourly marginal price for the Spanish bidding zone (EUR/MWh). |
| `price_portugal_eur_mwh`| `float64` | Hourly marginal price for the Portuguese bidding zone (EUR/MWh). |
| `energy_spain_mwh` | `float64` | Total cleared energy in Spain (MWh). |
| `energy_portugal_mwh` | `float64` | Total cleared energy in Portugal (MWh). |

---

## Usage

### With Python (`pandas` / `polars` / `duckdb`):

```python
import pandas as pd

# Load hourly marginal prices
df_prices = pd.read_parquet("data/omie_hourly_marginal_price.parquet")
print(f"Price range: {df_prices['price_spain_eur_mwh'].min()} to {df_prices['price_spain_eur_mwh'].max()} EUR/MWh")

# Load bidding curves (17M rows)
df_curves = pd.read_parquet("data/omie_bidding_curves_2024.parquet")
curve_hour_12 = df_curves[(df_curves["date"] == "2024-06-15") & (df_curves["hour"] == 12)]
print(f"Bidding steps in hour 12: {len(curve_hour_12)}")
```

---

## Applications and Research Use Cases

- **Reinforcement Learning (RL) and Battery Storage (BESS) Arbitrage**: Simulating and training RL agents for optimal charge/discharge cycles and co-located storage dispatch.
- **Short-Term Day-Ahead Price Forecasting**: Machine learning models predicting hourly marginal prices and price spikes.
- **Merit Order Dynamics and Renewable Impact**: Empirical analysis of supply curve shifts due to solar PV and wind generation.
- **Zero and Negative Price Modeling**: Probability modeling of renewable curtailment and market decoupling between Spain and Portugal.

---

## Provenance and Attribution

- **Source**: Operador del Mercado Ibérico de Energía (OMIE).
- **Terms of Use**: Publicly available data published by OMIE subject to source citation and attribution.
