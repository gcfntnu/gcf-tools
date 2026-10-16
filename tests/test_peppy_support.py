"""Compatibility of the exported PEP helpers for direct Python callers."""
from peppy_support import config2subsampletable, config_info


def test_single_read_subsample_helper_retains_its_table_return():
    config = {"samples": {"001": {"R1": "run/project/001_R1.fastq.gz"}}}
    info = config_info(config)
    assert not info["subsamples"]
    assert config2subsampletable(config, info).to_dict("records") == [
        {"sample_name": "001", "subsample_name": "001_1"}]
