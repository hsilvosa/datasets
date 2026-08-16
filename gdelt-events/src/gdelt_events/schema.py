from __future__ import annotations

import pyarrow as pa

COLUMNS = [
    "global_event_id",
    "event_date",
    "month_year",
    "year",
    "fraction_date",
    "actor1_code",
    "actor1_name",
    "actor1_country_code",
    "actor1_known_group_code",
    "actor1_ethnic_code",
    "actor1_religion1_code",
    "actor1_religion2_code",
    "actor1_type1_code",
    "actor1_type2_code",
    "actor1_type3_code",
    "actor2_code",
    "actor2_name",
    "actor2_country_code",
    "actor2_known_group_code",
    "actor2_ethnic_code",
    "actor2_religion1_code",
    "actor2_religion2_code",
    "actor2_type1_code",
    "actor2_type2_code",
    "actor2_type3_code",
    "is_root_event",
    "event_code",
    "event_base_code",
    "event_root_code",
    "quad_class",
    "goldstein_scale",
    "num_mentions",
    "num_sources",
    "num_articles",
    "avg_tone",
    "actor1_geo_type",
    "actor1_geo_full_name",
    "actor1_geo_country_code",
    "actor1_geo_adm1_code",
    "actor1_geo_latitude",
    "actor1_geo_longitude",
    "actor1_geo_feature_id",
    "actor2_geo_type",
    "actor2_geo_full_name",
    "actor2_geo_country_code",
    "actor2_geo_adm1_code",
    "actor2_geo_latitude",
    "actor2_geo_longitude",
    "actor2_geo_feature_id",
    "action_geo_type",
    "action_geo_full_name",
    "action_geo_country_code",
    "action_geo_adm1_code",
    "action_geo_latitude",
    "action_geo_longitude",
    "action_geo_feature_id",
    "date_added",
    "source_url",
]

STRING_COLUMNS = {
    name
    for name in COLUMNS
    if "code" in name or "name" in name or "feature_id" in name or name == "source_url"
}

FIELD_TYPES: dict[str, pa.DataType] = {name: pa.string() for name in STRING_COLUMNS}
FIELD_TYPES.update(
    {
        "global_event_id": pa.int64(),
        "event_date": pa.date32(),
        "month_year": pa.int32(),
        "year": pa.int16(),
        "fraction_date": pa.float64(),
        "is_root_event": pa.int8(),
        "quad_class": pa.int8(),
        "goldstein_scale": pa.float32(),
        "num_mentions": pa.int32(),
        "num_sources": pa.int32(),
        "num_articles": pa.int32(),
        "avg_tone": pa.float32(),
        "actor1_geo_type": pa.int8(),
        "actor1_geo_latitude": pa.float64(),
        "actor1_geo_longitude": pa.float64(),
        "actor2_geo_type": pa.int8(),
        "actor2_geo_latitude": pa.float64(),
        "actor2_geo_longitude": pa.float64(),
        "action_geo_type": pa.int8(),
        "action_geo_latitude": pa.float64(),
        "action_geo_longitude": pa.float64(),
        "date_added": pa.timestamp("s"),
    }
)

EVENT_SCHEMA = pa.schema([pa.field(name, FIELD_TYPES[name]) for name in COLUMNS]).append(
    pa.field("source_archive", pa.string(), nullable=False)
)
