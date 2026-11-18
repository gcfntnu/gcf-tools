"""Read-only project configuration preview before sequencing data arrives."""
from types import SimpleNamespace

import oyaml as yaml

from configmaker.configmaker import (apply_workflow_selection, create_default_config,
                                    merge_samples_with_submission_form, resolve_project_organism)
from configmaker.libprep import LibprepConfig
from configmaker.project_pairs import (PhysicalGeometryRequired, derive_project_geometry,
                                      validate_project_workbook)


def preview_project_config(project_id, samplesheet, workbook, *, libprep_config, run_info=None, machine=None):
    """Return a JSON-compatible result; only a generated result contains YAML."""
    validated = validate_project_workbook(project_id, samplesheet, workbook)
    report = validated.to_dict()
    report.update(kind="config_preview", preview_api_version=1, status="invalid", yaml=None,
                  runtime_inputs=["FASTQ paths and checksums", "observed run and instrument metadata"])
    if not validated.ok:
        return report
    try:
        if libprep_config is None:
            raise PhysicalGeometryRequired("Supply the workflow-owned libprep configuration.")
        snapshot = libprep_config if isinstance(libprep_config, LibprepConfig) else LibprepConfig.load(libprep_config)
        report["inputs"].append(dict(kind="libprep_config", path=snapshot.source, sha256=snapshot.sha256))
        if run_info is not None:
            from configmaker.validation import _read
            _, run_info = _read(run_info, "run_info", validated)
            report["inputs"].append(validated.inputs[-1])
            if run_info is None:
                report["errors"] = validated.to_dict()["errors"]
                return report
        reads = derive_project_geometry(validated.sheets[0], run_info)
        options = validated.custom_options
        selection = snapshot.select(options.get("Libprep"), reads)
        args = SimpleNamespace(_validation=validated, project_id=[project_id], new_project_id=None,
                               libkit=None, libprep_config=snapshot.source, organism=options.get("Organism"),
                               machine=machine, keep_batch=False, subsample=None, PI="NA",
                               contributor=None, title=None, summary="NA")
        resolve_project_organism(args, options, lambda: reads, snapshot=snapshot)
        samples = {item["sample_id"]: {"Sample_ID": item["sample_id"], "Project_ID": project_id}
                   for item in validated.summary["planned_samples"]}
        merged, descriptors = merge_samples_with_submission_form(samples, args)
        config = create_default_config(merged, options, args, descriptors=descriptors, planned_reads=reads)
        apply_workflow_selection(config, selection)
        report.update(yaml=yaml.safe_dump(config), status="generated")
    except PhysicalGeometryRequired as error:
        report.update(status="needs_input", missing=str(error))
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        report["errors"].append(dict(severity="error", code="preview.configuration", project_id=project_id,
                                     message=str(error)))
    return report
