"""Portable sample/library metadata contract for GCF project configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class MetadataTables:
    """Normalized biological-sample and technical-library metadata tables."""

    sample_info: pd.DataFrame
    library_info: pd.DataFrame


def _as_mapping(value: Any, name: str) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"config['{name}'] must be a non-empty mapping")

    for key, record in value.items():
        if not isinstance(record, Mapping):
            raise ValueError(f"config['{name}']['{key}'] must be a mapping")
    return value


def _canonical_id(key: Any, record: Mapping[str, Any], columns: tuple[str, ...], label: str) -> str:
    key = str(key)
    embedded = [str(record[column]) for column in columns if column in record and pd.notna(record[column])]

    if embedded and any(value != key for value in embedded):
        raise ValueError(f"{label} key '{key}' disagrees with embedded identity {embedded}")
    if len(set(embedded)) > 1:
        raise ValueError(f"{label} '{key}' contains conflicting embedded identities {embedded}")

    return key


def metadata_tables_from_config(config: Mapping[str, Any]) -> MetadataTables:
    """Materialize biological sample and technical library tables from project config.

    Legacy configs contain only samples and therefore imply one technical
    library per biological sample with the same identifier. Future configs may
    provide an explicit libraries mapping whose records reference Sample_ID
    (or sample_id).

    Values are preserved as supplied. This function only validates identities
    and relationships; it does not normalize labels, coerce values, or infer
    biological meaning.

    Parameters
    ----------
    config
        Project configuration mapping.

    Returns
    -------
    MetadataTables
        sample_info indexed by Sample_ID and library_info indexed by library_id.

    Raises
    ------
    ValueError
        If identities are missing, conflicting, duplicated, or reference an
        unknown biological sample.
    """
    samples = _as_mapping(config.get("samples"), "samples")

    sample_rows = []
    for key, record in samples.items():
        sample_id = _canonical_id(key, record, ("Sample_ID", "sample_id"), "sample")
        row = dict(record)
        row.pop("sample_id", None)
        row["Sample_ID"] = sample_id
        sample_rows.append(row)

    sample_info = pd.DataFrame(sample_rows).set_index("Sample_ID", drop=False)
    if not sample_info.index.is_unique:
        raise ValueError("Sample_ID values must be unique")

    libraries = config.get("libraries")
    library_rows = []

    if libraries is None:
        for sample_id in sample_info.index:
            library_rows.append({"library_id": sample_id, "Sample_ID": sample_id})
    else:
        libraries = _as_mapping(libraries, "libraries")
        for key, record in libraries.items():
            library_id = _canonical_id(key, record, ("library_id", "Library_ID"), "library")

            sample_values = [
                str(record[column])
                for column in ("Sample_ID", "sample_id")
                if column in record and pd.notna(record[column])
            ]
            if not sample_values:
                raise ValueError(f"library '{library_id}' is missing Sample_ID")
            if len(set(sample_values)) != 1:
                raise ValueError(f"library '{library_id}' contains conflicting Sample_ID values {sample_values}")

            sample_id = sample_values[0]
            if sample_id not in sample_info.index:
                raise ValueError(f"library '{library_id}' references unknown Sample_ID '{sample_id}'")

            row = dict(record)
            row.pop("Library_ID", None)
            row.pop("sample_id", None)
            row["library_id"] = library_id
            row["Sample_ID"] = sample_id
            library_rows.append(row)

    library_info = pd.DataFrame(library_rows).set_index("library_id", drop=False)
    if not library_info.index.is_unique:
        raise ValueError("library_id values must be unique")

    return MetadataTables(sample_info=sample_info, library_info=library_info)
