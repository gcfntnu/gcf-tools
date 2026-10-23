"""Synthetic independent project metadata and complete-flowcell assignments."""

import hashlib
import json

import pytest

from configmaker.libprep import LibprepConfig, LibprepConfigError
from configmaker.project_pairs import derive_project_geometry, resolve_project_pairs, validate_project_pairs
from test_validation import customer_row, sample_sheet, submission_form

A, B, C = "GCF-2099-001", "GCF-2099-002", "GCF-2099-003"


def pair(root, project, sample, index, *, options="", settings="", lane="1"):
    sheet = sample_sheet(root / (project + "_SampleSheet.csv"), [[sample, project, lane, index, "ACGTACGT"]],
                         headers=["Sample_ID", "Sample_Project", "Lane", "index", "index2"])
    sheet.write_text("[Reads]\n75\n150\n" + options + settings + sheet.read_text())
    form = submission_form(root / (project + "_Sample-Submission-Form.xlsx"), [customer_row(sample, project=project)])
    return sheet, form


def run_info(path):
    path.write_text('<RunInfo><Run><Reads><Read Number="1" NumCycles="75" IsIndexedRead="N"/>'
                    '<Read Number="2" NumCycles="8" IsIndexedRead="Y"/>'
                    '<Read Number="3" NumCycles="8" IsIndexedRead="Y"/>'
                    '<Read Number="4" NumCycles="150" IsIndexedRead="N"/>'
                    '</Reads><FlowcellLayout LaneCount="2"/></Run></RunInfo>')
    return path


def codes(result):
    return {finding["code"] for finding in result.findings if finding["severity"] == "error"}


def test_pairing_is_sorted_hash_bound_non_mutating_and_qualified_copy_wins(tmp_path):
    sa, fa = pair(tmp_path, A, "A", "AAAAAAAA")
    sb, fb = pair(tmp_path, B, "B", "CCCCCCCC")
    duplicate = tmp_path / "SampleSheet.csv"
    duplicate.write_bytes(sa.read_bytes())
    originals = {str(path): path.read_bytes() for path in (sa, fa, sb, fb, duplicate)}
    result = resolve_project_pairs([sb, duplicate, sa], [fb, fa])
    assert result.ok, result.render_text()
    assert [item.project_id for item in result.pairs] == [A, B]
    assert result.duplicates == [{"path": str(duplicate), "retained": str(sa), "sha256": hashlib.sha256(sa.read_bytes()).hexdigest()}]
    assert result.to_dict() == resolve_project_pairs([sa, sb, duplicate], [fa, fb]).to_dict()
    for item in result.inputs:
        assert item["sha256"] == hashlib.sha256(originals[item["path"]]).hexdigest()
    assert all(path.read_bytes() == originals[str(path)] for path in (sa, fa, sb, fb, duplicate))
    json.dumps(result.to_dict())


@pytest.mark.parametrize("problem,expected", [
    ("missing", "pair.count_mismatch"), ("different_keys", "pair.project_set_mismatch"),
    ("duplicate_form", "pair.duplicate_submission_form"), ("different_sheet", "pair.duplicate_samplesheet"),
    ("unqualified", "pair.missing_filename_key"), ("ambiguous", "pair.ambiguous_filename"),
    ("identical_other_project", "pair.identical_cross_project_sheets"),
])
def test_pairing_rejects_count_key_and_candidate_conflicts(tmp_path, problem, expected):
    sa, fa = pair(tmp_path, A, "A", "AAAAAAAA")
    sb, fb = pair(tmp_path, B, "B", "CCCCCCCC")
    sheets, forms = [sa, sb], [fa, fb]
    if problem == "missing":
        forms.pop()
    elif problem == "different_keys":
        fc = tmp_path / (C + "_form.xlsx")
        fb.rename(fc)
        forms[1] = fc
    elif problem == "duplicate_form":
        duplicate = tmp_path / (A + "_other_form.xlsx")
        duplicate.write_bytes(fa.read_bytes())
        forms.append(duplicate)
    elif problem == "different_sheet":
        duplicate = tmp_path / (A + "_other_sheet.csv")
        duplicate.write_bytes(sa.read_bytes() + b"\n")
        sheets.append(duplicate)
    elif problem == "unqualified":
        generic = tmp_path / "SampleSheet.csv"
        sb.rename(generic)
        sheets[1] = generic
    elif problem == "ambiguous":
        ambiguous = tmp_path / (A + "_" + B + "_sheet.csv")
        sb.rename(ambiguous)
        sheets[1] = ambiguous
    else:
        sb.write_bytes(sa.read_bytes())
    result = resolve_project_pairs(sheets, forms)
    assert expected in codes(result), result.render_text()


def test_deduplicated_generic_single_pair_keeps_legacy_multi_project_content(tmp_path):
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [["A", A], ["B", B]])
    duplicate = tmp_path / "SampleSheet_copy.csv"
    duplicate.write_bytes(sheet.read_bytes())
    form = submission_form(tmp_path / "submission.xlsx", [customer_row("A", project=A), customer_row("B", project=B)])
    result = resolve_project_pairs([duplicate, sheet], [form])
    assert result.ok
    assert result.mode == "legacy"
    assert result.pairs[0].project_id is None
    validated = validate_project_pairs([duplicate, sheet], [form])
    assert validated.ok, validated.render_text()
    assert len(validated.project_results["legacy"].summary["projects"]) == 2
    assert not validated.assignments


def test_wrong_projects_form_cannot_supply_missing_sample(tmp_path):
    sa, fa = pair(tmp_path, A, "A", "AAAAAAAA")
    sb, fb = pair(tmp_path, B, "B", "CCCCCCCC")
    submission_form(fa, [customer_row("EXTRA", project=A)])
    submission_form(fb, [customer_row("B", project=B), customer_row("A", project=B)])
    result = validate_project_pairs([sa, sb], [fa, fb])
    assert "sample.missing_metadata" in codes(result)
    missing = next(finding for finding in result.findings if finding["code"] == "sample.missing_metadata")
    assert missing["project_id"] == A and missing["file"] == str(sa)
    assert result.project_results[B].ok
    assert "Project " + A in result.render_text()


def test_single_qualified_pair_keeps_legacy_multi_project_content_after_dedup(tmp_path):
    sheet = sample_sheet(tmp_path / (A + "_SampleSheet.csv"), [["A", A], ["B", B]])
    sheet.write_text("[Settings]\nIndependentIndexCollisionCheck,1\n" + sheet.read_text())
    generic = tmp_path / "SampleSheet.csv"
    generic.write_bytes(sheet.read_bytes())
    form = submission_form(tmp_path / (A + "_Sample-Submission-Form.xlsx"),
                           [customer_row("A", project=A), customer_row("B", project=B)])
    result = validate_project_pairs([generic, sheet], [form])
    assert result.ok and result.mode == "legacy", result.render_text()
    assert result.pairs[0].sample_sheet == str(sheet)
    assert len(result.project_results["legacy"].summary["projects"]) == 2


def test_project_preparations_settings_metadata_and_geometry_stay_independent(tmp_path):
    sa, fa = pair(tmp_path, A, "A", "AAAAAAAA", options="[CustomOptions]\nLibprep,Alpha\nOrganism,Human\n",
                  settings="[Settings]\nOverrideCycles,Y75;I8;I8;N150\n")
    sb, fb = pair(tmp_path, B, "B", "CCCCCCCC", options="[CustomOptions]\nLibprep,Beta\nOrganism,Mouse\n")
    snapshot = LibprepConfig("synthetic snapshot", b"Alpha SE:\n  workflow: rnaseq\nBeta PE:\n  workflow: chipseq\n")
    result = validate_project_pairs([sa, sb], [fa, fb], run_info=run_info(tmp_path / "RunInfo.xml"), libprep_config=snapshot)
    assert result.ok, result.render_text()
    assert result.project_geometry == {A: [75], B: [75, 150]}
    assert result.selections[A]["workflow"] == "rnaseq" and result.selections[B]["workflow"] == "chipseq"
    assert result.selections[A]["sha256"] == result.selections[B]["sha256"] == snapshot.sha256
    assert result.project_results[A].custom_options["Organism"] == "Human"
    assert result.project_results[B].custom_options["Organism"] == "Mouse"
    assert list(result.project_results[A].metadata.Sample_ID) == ["A"]
    assert list(result.project_results[B].metadata.Sample_ID) == ["B"]
    assert result.assignments[0]["source_sheet"] == str(sa)
    assert result.assignments[0]["effective_read_geometry"] == [75]
    json.dumps(result.to_dict())


@pytest.mark.parametrize("change,expected", [
    ("index", "demux.index_collision"), ("mismatch", "demux.index_collision"),
    ("id", "demux.cross_project_sample_id"), ("lane", "demux.invalid_lane"),
    ("cycles", "demux.project_geometry"), ("index_cycles", "demux.index_geometry"),
    ("symbolic_index", "index.unknown_name"), ("global_setting", "demux.incompatible_settings"),
    ("independent_collision", "demux.unsupported_collision_policy"),
    ("sheet_project", "pair.sheet_project_conflict"), ("form_project", "pair.form_project_conflict"),
])
def test_whole_flowcell_conflicts_are_blocking(tmp_path, change, expected):
    sa, fa = pair(tmp_path, A, "A", "AAAAAAAA")
    sb, fb = pair(tmp_path, B, "B", "CCCCCCCC")
    if change == "index":
        sb.write_text(sb.read_text().replace("CCCCCCCC", "AAAAAAAA"))
    elif change == "mismatch":
        sb.write_text(sb.read_text().replace("CCCCCCCC", "AAAAAACC"))
    elif change == "id":
        sb.write_text(sb.read_text().replace("B," + B, "A," + B))
        submission_form(fb, [customer_row("A", project=B)])
    elif change == "lane":
        sb.write_text(sb.read_text().replace(",1,CCCC", ",3,CCCC"))
    elif change == "cycles":
        sb.write_text("[Settings]\nOverrideCycles,Y76;I8;I8;Y150\n" + sb.read_text())
    elif change == "index_cycles":
        sb.write_text(sb.read_text().replace("CCCCCCCC", "CCCCCCCCCC"))
    elif change == "symbolic_index":
        sb.write_text(sb.read_text().replace("CCCCCCCC", "SI-TT-SYNTHETIC"))
    elif change == "global_setting":
        sb.write_text("[Settings]\nMinimumTrimmedReadLength,20\n" + sb.read_text())
    elif change == "independent_collision":
        sa.write_text("[Settings]\nIndependentIndexCollisionCheck,1\n" + sa.read_text())
        sb.write_text("[Settings]\nIndependentIndexCollisionCheck,1\n" + sb.read_text())
    elif change == "sheet_project":
        sb.write_text(sb.read_text().replace(B, C))
    else:
        submission_form(fb, [customer_row("B", project=C)])
    result = validate_project_pairs([sa, sb], [fa, fb], run_info=run_info(tmp_path / "RunInfo.xml"))
    assert expected in codes(result), result.render_text()


def test_explicit_zero_mismatches_and_disjoint_lanes_do_not_collide(tmp_path):
    sa, fa = pair(tmp_path, A, "A", "AAAAAAAA", lane="1")
    sb, fb = pair(tmp_path, B, "B", "AAAAAACC", lane="2")
    assert validate_project_pairs([sa, sb], [fa, fb]).ok
    sb.write_text(sb.read_text().replace(",2,", ",1,"))
    assert not validate_project_pairs([sa, sb], [fa, fb]).ok
    assert validate_project_pairs([sa, sb], [fa, fb], mismatch_policy=0).ok


def test_row_overrides_and_star_cycles_use_physical_geometry(tmp_path):
    sheet, _ = pair(tmp_path, A, "A", "AAAAAAAA")
    sheet.write_text(sheet.read_text().replace("index2\n", "index2,OverrideCycles\n").replace(",ACGTACGT\n", ",ACGTACGT,Y*;I8;I8;Y100N50\n"))
    assert derive_project_geometry(sheet, run_info=run_info(tmp_path / "RunInfo.xml")) == [75, 100]
    with pytest.raises(LibprepConfigError, match="physical"):
        derive_project_geometry(sheet)


def test_shortened_index_cycles_are_validated_against_effective_mask(tmp_path):
    sa, fa = pair(tmp_path, A, "A", "AAAAAA", settings="[Settings]\nOverrideCycles,Y75;I6N2;I8;Y150\n")
    sb, fb = pair(tmp_path, B, "B", "CCCCCCCC")
    info = run_info(tmp_path / "RunInfo.xml")
    assert validate_project_pairs([sa, sb], [fa, fb], run_info=info).ok
    sb.write_text(sb.read_text().replace("CCCCCCCC", "CCCCCC"))
    assert "demux.index_geometry" in codes(validate_project_pairs([sa, sb], [fa, fb], run_info=info))
