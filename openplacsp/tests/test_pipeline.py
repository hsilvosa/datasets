import json
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

from openplacsp_pipeline.analyze import analyze
from openplacsp_pipeline.config import Config
from openplacsp_pipeline.normalize import normalize
from openplacsp_pipeline.publish import stage
from openplacsp_pipeline.tasks import build_tasks

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def make_config(root: Path) -> Config:
    return Config(
        raw_dir=root / "raw",
        processed_dir=root / "processed",
        artifacts_dir=root / "artifacts",
        staging_dir=root / "staging",
        start_year=2025,
        end_year=2025,
        end_month=12,
        monthly_from_year=2025,
        max_archives=1,
        timeout_seconds=10,
        max_retries=0,
        parquet_rows_per_file=1,
        user_agent="test",
    )


def test_task_plan_can_use_monthly_archives(tmp_path):
    task = build_tasks(make_config(tmp_path))[0]
    assert task.period == "202501"
    assert task.url.endswith("_202501.zip")


def test_offline_pipeline(tmp_path):
    config = make_config(tmp_path)
    config.raw_dir.mkdir(parents=True)
    with zipfile.ZipFile(config.raw_dir / "fixture.zip", "w") as archive:
        archive.write(FIXTURE, "sample.atom")
    summary = normalize(config)
    assert summary["tables"] == {"versions": 2, "lots": 1, "cpv_codes": 2, "awards": 1}
    versions = pq.read_table(config.processed_dir / "versions")
    assert versions.num_rows == 2
    assert str(versions.schema.field("updated_at").type) == "timestamp[us, tz=UTC]"
    profile = analyze(config)
    assert profile["tables"]["versions"]["row_count"] == 2
    quality = json.loads((config.artifacts_dir / "quality.json").read_text(encoding="utf-8"))
    assert quality["checks_passed"] is True
    staged = stage(config)
    assert (staged / "README.md").exists()
    assert (staged / "data" / "awards" / "part-00000.parquet").exists()
