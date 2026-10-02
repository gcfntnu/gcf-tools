import pytest

from configmaker.metadata import metadata_tables_from_config


def test_legacy_samples_imply_one_library_per_sample():
    config = {
        "samples": {
            "S1": {"Sample_Group": "control", "RIN": "<5"},
            "S2": {"Sample_Group": "treated", "RIN": "3-7"},
        }
    }

    tables = metadata_tables_from_config(config)

    assert tables.sample_info.index.tolist() == ["S1", "S2"]
    assert tables.sample_info.loc["S1", "RIN"] == "<5"
    assert tables.sample_info.loc["S2", "RIN"] == "3-7"
    assert tables.library_info.to_dict("records") == [
        {"library_id": "S1", "Sample_ID": "S1"},
        {"library_id": "S2", "Sample_ID": "S2"},
    ]


def test_explicit_libraries_support_multiple_libraries_per_sample():
    config = {
        "samples": {
            "donor_A": {"condition": "control"},
            "donor_B": {"condition": "treated"},
        },
        "libraries": {
            "lib_A1": {"Sample_ID": "donor_A", "chemistry": "10x_v4"},
            "lib_A2": {"sample_id": "donor_A", "chemistry": "10x_v4"},
            "lib_B1": {"Sample_ID": "donor_B", "chemistry": "10x_v4"},
        },
    }

    tables = metadata_tables_from_config(config)

    assert tables.library_info["Sample_ID"].tolist() == ["donor_A", "donor_A", "donor_B"]
    assert tables.library_info.loc["lib_A2", "chemistry"] == "10x_v4"


def test_values_are_not_normalized_or_coerced():
    config = {
        "samples": {
            "001": {
                "marker": "IL-6/A+B",
                "limit": "<5",
                "range": "3-7",
                "unicode": "ødem",
            }
        }
    }

    sample_info = metadata_tables_from_config(config).sample_info

    assert sample_info.loc["001", "marker"] == "IL-6/A+B"
    assert sample_info.loc["001", "limit"] == "<5"
    assert sample_info.loc["001", "range"] == "3-7"
    assert sample_info.loc["001", "unicode"] == "ødem"


@pytest.mark.parametrize(
    "config,match",
    [
        (
            {"samples": {"S1": {}}, "libraries": {"L1": {"Sample_ID": "S2"}}},
            "references unknown Sample_ID",
        ),
        (
            {"samples": {"S1": {"Sample_ID": "S2"}}},
            "disagrees with embedded identity",
        ),
        (
            {
                "samples": {"S1": {}},
                "libraries": {"L1": {"library_id": "L2", "Sample_ID": "S1"}},
            },
            "disagrees with embedded identity",
        ),
        (
            {"samples": {"S1": {}}, "libraries": {"L1": {"chemistry": "10x_v4"}}},
            "missing Sample_ID",
        ),
    ],
)
def test_invalid_identity_relationships_fail(config, match):
    with pytest.raises(ValueError, match=match):
        metadata_tables_from_config(config)
