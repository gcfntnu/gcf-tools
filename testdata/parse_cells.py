"""Explicit WT v4 native-barcode filtering; no cell calling or barcode correction."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
import gzip
import json
import multiprocessing
import re
import sys

from testdata.create_testdata import _component, paired_records, write_fastq_checksums

PROFILE = "parse-wt-v4-cells"
ALGORITHM = "parse-wt-v4-exact-cell-keys-v1; R2[10:18]+R2[30:38]+R2[50:58]; all matching pairs in source order"
_CANCEL = None


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key: {!r}".format(key))
        result[key] = value
    return result


def _fields(value, expected, context):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("{} requires exactly fields {}".format(context, ", ".join(sorted(expected))))


def validate_selection(content, source):
    """Validate schema and authoritative metadata before opening any FASTQs."""
    data = json.loads(content, object_pairs_hook=_unique_object)
    _fields(data, {"schema_version", "profile", "read_lengths", "minimum_signal_pairs",
                   "biological_samples", "sublibraries"}, "Parse selection")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["profile"] != PROFILE:
        raise ValueError("Only schema_version 1 / profile {} is supported".format(PROFILE))
    if (data["read_lengths"] != [64, 58]
            or any(type(value) is not int for value in data["read_lengths"])):
        raise ValueError("Parse profile requires read_lengths [64, 58]")
    minimum = data["minimum_signal_pairs"]
    if type(minimum) is not int or minimum < 1:
        raise ValueError("minimum_signal_pairs must be a positive integer")
    settings = source.selection.parameters
    quant = settings.get("quant", {})
    if (source.selection.entry != "Parse Biosciences Evercode WT v4 PE"
            or source.selection.read_geometry != (64, 58) or source.pipeline != "singlecell"
            or not isinstance(quant, dict) or quant.get("method") != "splitpipe"
            or quant.get("kit") != "WT" or quant.get("chemistry") != "v4"
            or quant.get("assay", "wt") != "wt"):
        raise ValueError("Parse profile requires WT v4 gene expression, Split-Pipe and Stats geometry 64/58")
    biological = data["biological_samples"]
    libraries = data["sublibraries"]
    for name, mapping in (("biological_samples", biological), ("sublibraries", libraries)):
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("{} must be a nonempty mapping".format(name))
        for identity in mapping:
            _component(identity, name + " ID")
    demux_info = source._validation.forms[0].get("demux")
    if demux_info is None or "Wells" not in demux_info["data"]:
        raise ValueError("Prepared Cell Multiplexing requires a populated Wells column")
    demux = demux_info["data"]
    wells = dict(zip(demux["Sample_ID"], demux["Wells"]))
    if any(not isinstance(value, str) or not value or not value.isascii() for value in wells.values()):
        raise ValueError("Prepared Cell Multiplexing requires nonempty ASCII Wells for every biological sample")
    if set(wells) != set(biological):
        raise ValueError("Manifest biological samples must exactly match the prepared Cell Multiplexing sheet")
    for identity, info in biological.items():
        _fields(info, {"wells"}, "Biological sample")
        if (not isinstance(info["wells"], str) or not info["wells"]
                or not info["wells"].isascii() or info["wells"] != wells[identity]):
            raise ValueError("Manifest wells must exactly match Cell Multiplexing for {!r}".format(identity))
    for library, info in libraries.items():
        if library not in source.fastq_files:
            raise ValueError("Unknown exact sublibrary: {!r}".format(library))
        _fields(info, {"cells"}, "Sublibrary")
        cells = info["cells"]
        if not isinstance(cells, list) or not cells:
            raise ValueError("Sublibrary cells must be a nonempty list")
        identities, keys, signal_samples = set(), set(), set()
        for cell in cells:
            _fields(cell, {"cell_id", "biological_sample", "role", "r2_keys"}, "Cell")
            identity = _component(cell["cell_id"], "Cell ID")
            if identity in identities:
                raise ValueError("Duplicate cell_id within sublibrary {!r}".format(library))
            identities.add(identity)
            biological_id = cell["biological_sample"]
            if not isinstance(biological_id, str) or biological_id not in biological:
                raise ValueError("Unknown cell biological_sample")
            if cell["role"] not in ("signal", "background"):
                raise ValueError("Cell role must be signal or background")
            if cell["role"] == "signal":
                signal_samples.add(biological_id)
            if not isinstance(cell["r2_keys"], list) or not cell["r2_keys"]:
                raise ValueError("Cell r2_keys must be a nonempty list")
            for key in cell["r2_keys"]:
                if not isinstance(key, str) or re.fullmatch("[ACGT]{24}", key) is None:
                    raise ValueError("Each native R2 key must contain exactly 24 uppercase ACGT bases")
                if key in keys:
                    raise ValueError("Duplicate or ambiguous R2 key within sublibrary {!r}".format(library))
                keys.add(key)
        if signal_samples != set(biological):
            raise ValueError("Every sublibrary must select signal cells for every biological sample")
    return data


class _Cancelled(RuntimeError):
    pass


def _initialize_worker(cancel):
    global _CANCEL
    _CANCEL = cancel


def _filter_library(library, pair, cells, minimum, project, cancel=None):
    """One worker owns only this library's two files; parent owns publication."""
    cancel = cancel if cancel is not None else _CANCEL
    key_to_cell = {key.encode("ascii"): cell["cell_id"] for cell in cells for key in cell["r2_keys"]}
    counts = {cell["cell_id"]: 0 for cell in cells}
    key_counts = {key: 0 for key in key_to_cell}
    total, retained = 0, 0
    try:
        if cancel.is_set():
            raise _Cancelled("Parse extraction cancelled after another worker failed")
        with ExitStack() as stack:
            writers = []
            for mate in (1, 2):
                handle = stack.enter_context((project / (library + "_R{}.fastq.gz".format(mate))).open("xb"))
                writers.append(stack.enter_context(gzip.GzipFile(filename="", mode="wb", fileobj=handle,
                                                                 mtime=0, compresslevel=9)))
            for _, first, second in paired_records(*pair):
                total += 1
                # Shared parser has already validated the complete record; extract sequence only.
                seq1, seq2 = first.split(b"\n", 2)[1], second.split(b"\n", 2)[1]
                if len(seq1) != 64 or len(seq2) != 58:
                    raise ValueError("Parse read geometry differs from 64/58 in {} at pair {}".format(library, total))
                key = seq2[10:18] + seq2[30:38] + seq2[50:58]
                cell = key_to_cell.get(key)
                if cell is not None:
                    writers[0].write(first)
                    writers[1].write(second)
                    counts[cell] += 1
                    key_counts[key] += 1
                    retained += 1
                if total % 10000 == 0 and cancel.is_set():
                    raise _Cancelled("Parse extraction cancelled after another worker failed")
                if total % 5000000 == 0:
                    print("Parse {}: scanned {} pairs; retained {}".format(library, total, retained), file=sys.stderr, flush=True)
        if not total:
            raise ValueError("Parse FASTQ pair is empty: " + library)
        insufficient = [cell["cell_id"] for cell in cells
                        if cell["role"] == "signal" and counts[cell["cell_id"]] < minimum]
        if insufficient:
            raise ValueError("{} signal cells in {} have fewer than minimum_signal_pairs={}".format(len(insufficient), library, minimum))
        print("Parse {}: complete; scanned {} pairs; retained {}".format(library, total, retained), file=sys.stderr, flush=True)
        return {"available_pairs": total, "selected_pairs": retained, "cells": counts,
                "r2_keys": {key.decode("ascii"): count for key, count in key_counts.items()},
                "input_sha256": [item.sha256 for item in pair]}
    except BaseException:
        cancel.set()
        raise


def _extract_libraries(pairs, selection, project):
    context = multiprocessing.get_context("spawn")
    cancel = context.Event()
    results, errors, futures = {}, [], {}
    with ProcessPoolExecutor(max_workers=min(2, len(pairs)), mp_context=context,
                             initializer=_initialize_worker, initargs=(cancel,)) as pool:
        try:
            for library, pair in pairs.items():
                future = pool.submit(_filter_library, library, pair, selection["sublibraries"][library]["cells"],
                                     selection["minimum_signal_pairs"], project)
                futures[future] = library
            for future in as_completed(futures):
                try:
                    results[futures[future]] = future.result()
                except Exception as error:
                    cancel.set()
                    errors.append(error)
            if errors:
                raise next((error for error in errors if not isinstance(error, _Cancelled)), errors[0])
        finally:
            cancel.set()
            for future in futures:
                future.cancel()
    return results


def generate_parse_cells(source, output_dir, selection_path):
    selection_input = source._capture(selection_path)
    selection_bytes = selection_input.read()
    selection = validate_selection(selection_bytes, source)
    with source._generation(output_dir, list(selection["sublibraries"])) as (stage, pairs, destination):
        results = _extract_libraries(pairs, selection, stage / source._gcf_number)
        for library, result in results.items():
            for item, digest in zip(pairs[library], result.pop("input_sha256")):
                item.sha256 = digest
        manifest = source._provenance()
        manifest.update(profile=PROFILE, algorithm=ALGORITHM, selection_sha256=selection_input.sha256,
                        read_lengths=selection["read_lengths"], minimum_signal_pairs=selection["minimum_signal_pairs"],
                        biological_samples=selection["biological_samples"], sublibraries=selection["sublibraries"],
                        samples=results, output_fastq_sha256=write_fastq_checksums(stage, source._gcf_number),
                        limitations="Exact native barcode matching; no error correction or barcode-to-well inference; WT gene expression only")
        (stage / "testdata.provenance.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return destination
