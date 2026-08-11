from pathlib import Path

from aemps_cima.config import Config


def test_config_resolves_data_paths_from_project_directory() -> None:
    config = Config.load(Path(__file__).parents[1] / "configs" / "sample.json")
    assert config.raw_dir.name == "raw"
    assert config.raw_dir.parent.name == "sample"
    assert config.max_medications == 5
