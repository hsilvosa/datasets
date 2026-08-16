from __future__ import annotations

import pyarrow as pa

from safecast_historical.normalize import SOURCE_COLUMNS, transform


def test_transform_types_and_names() -> None:
    row = [
        "2026-08-14 01:59:37",
        59.4397,
        25.5189,
        24.0,
        "cpm",
        None,
        None,
        "ad4246727be44a2758f50b59bb454c30",
        None,
        None,
        None,
        "2026-08-14 01:59:41.293514",
        None,
    ]
    arrays = [pa.array([value]) for value in row]
    source = pa.Table.from_arrays(arrays, names=SOURCE_COLUMNS)
    result = transform(source)
    assert result.column_names[0:3] == ["captured_at", "latitude", "longitude"]
    assert result["captured_at"][0].as_py().year == 2026
    assert result["uploaded_at"][0].as_py().microsecond == 293514
    assert result["unit"][0].as_py() == "cpm"
