"""Wholly invented native-key pairs; no vendor sequences or scientific workflow."""
import json
from openpyxl import load_workbook

from multiplexed_fixture import make_multiplexed, KIT as STUB_KIT
from producer_fixture import PROJECT, records, write_records

KIT = "Parse Biosciences Evercode WT v4"
BIO = {"001": {"wells": "A1, A2"}, "1": {"wells": "B1-B2"}}
KEYS = ["A" * 24, "C" * 24, "G" * 24, "T" * 24, "ACGT" * 6, "TGCA" * 6, "AGCT" * 6]


def parse_source(root):
    run, form, work = make_multiplexed(root)
    sheet = run / "SampleSheet.csv"
    sheet.write_text(sheet.read_text().replace(STUB_KIT, KIT).replace("CTRL," + PROJECT + "\n", ""))
    book = load_workbook(form)
    book["Sample-Submission-Form"].delete_rows(18)
    book["INFO (GCF-lab only)"].delete_rows(4)
    book.save(form)
    config = work / "src/gcf-workflows/libprep.config"
    config.write_text(KIT + " PE:\n  workflow: singlecell\n  quant:\n    method: splitpipe\n    kit: WT\n    chemistry: v4\n    assay: wt\n")
    (work / "src/gcf-workflows/singlecell").mkdir()
    (work / "src/gcf-workflows/singlecell/singlecell.smk").write_text('raise RuntimeError("Synthetic initialization only; no scientific processing")\n')
    stats = run / "Stats/Stats.json"
    data = json.loads(stats.read_text())
    for lane in data["ReadInfosForLanes"]:
        for read, length in zip(lane["ReadInfos"], [64, 58]):
            read["NumCycles"] = length
    stats.write_text(json.dumps(data))
    (run / "RunInfo.xml").write_bytes(b'<RunInfo><Run Id="synthetic"/></RunInfo>\n')
    for path in (run / PROJECT).glob("CTRL*"):
        path.unlink()
    selection = {"schema_version": 1, "profile": "parse-wt-v4-cells", "read_lengths": [64, 58],
                 "minimum_signal_pairs": 4, "biological_samples": BIO, "sublibraries": {}}
    expected = {}
    for library in ("001", "001A"):
        selection["sublibraries"][library] = {"cells": [
            {"cell_id": "cellA", "biological_sample": "001", "role": "signal", "r2_keys": KEYS[:2]},
            {"cell_id": "cellB", "biological_sample": "1", "role": "signal", "r2_keys": KEYS[2:4]},
            {"cell_id": "backgroundA", "biological_sample": "001", "role": "background", "r2_keys": [KEYS[4]]},
            {"cell_id": "backgroundB", "biological_sample": "1", "role": "background", "r2_keys": [KEYS[5]]},
        ]}
        expected[library] = []
        for mate in (1, 2):
            path = run / PROJECT / (library + "_R{}.fastq.gz".format(mate))
            rows = [list(row) for row in records(path)]
            for index, row in enumerate(rows):
                key_index = min(index % 8, 6)
                key = KEYS[key_index]
                row[1] = (row[1][:64] if mate == 1 else
                          "ACGTACGTAC" + key[:8] + "ACGTACGTACGT" + key[8:16] + "TGCATGCATGCA" + key[16:])
                row[3] = "I" * len(row[1])
                if mate == 1 and key_index < 6:
                    expected[library].append(row[0].rsplit("/", 1)[0])
            write_records(path, rows)
    manifest = root / "selection.json"
    manifest.write_text(json.dumps(selection, indent=2) + "\n")
    return run, config, manifest, work, expected
