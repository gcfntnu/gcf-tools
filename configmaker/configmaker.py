#!/usr/bin/env python

import copy
import sys
import os
import re
import glob
import logging
import json
import warnings
import subprocess
import re
import pprint
import shutil
from pathlib import Path
from collections.abc import Iterable
import six


import argparse
import pandas as pd
import oyaml as yaml

# enable local imports in script
# path_root = Path(__file__).parents[0]
# sys.path.append(str(path_root))

import descriptors
if __name__ == "__main__":
    # Legacy setup.py installs execute an egg script through a bin wrapper;
    # remove both locations so configmaker.py cannot shadow the package.
    script_dirs = {Path(__file__).resolve().parent, Path(sys.argv[0]).resolve().parent}
    sys.path[:] = [p for p in sys.path if Path(p or os.curdir).resolve() not in script_dirs]
from configmaker.libprep import LibprepConfig, LibprepConfigError, find_read_geometry
from configmaker.validation import (validate_inputs, ValidationResult, InputValidationError,
                                   parse_samplesheet, parse_submission_form, VALIDATOR_VERSION)


SEQUENCERS = {
    "NB501038": "NextSeq 500",
    "SN7001334": "HiSeq 2500",
    "K00251": "HiSeq 4000",
    "M02675": "MiSeq NTNU",
    "M03942": "MiSeq StOlav",
    "M05617": "MiSeq SINTEF",
    "M71102": "MiSeq MolPat",
    "A01990": "NovaSeq 6000",
    "MN00686": "MiniSeq NTNU",
}

GCF_WORKFLOWS_SRC = "https://github.com/gcfntnu/gcf-workflows.git"

SNAKEFILE_TEMPLATE = """
from snakemake.utils import validate, min_version

pepfile:
    'pep/pep_config.yaml'
configfile:
    'config.yaml'

include:
    'src/gcf-workflows/{workflow}/{workflow}.smk'

"""


def setup_logger(verbose=False):
    """Configure console logging only when the standalone application starts."""
    logger = logging.getLogger("GCF-configmaker")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    return logger


logger = logging.getLogger("GCF-configmaker")


def uniq_list():
    """
    list of uniq values order is preserved.
    """
    out = []
    [out.append(i) for i in seq if not out.count(i)]
    return out


class FullPaths(argparse.Action):
    """
    Expand user- and relative-paths.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        values = [os.path.abspath(os.path.expanduser(v)) for v in values]
        setattr(namespace, self.dest, values)


def is_dir(dirname):
    """
    Checks if a path is an actual directory.
    """
    if not os.path.isdir(dirname):
        msg = "{0} is not a directory".format(dirname)
        raise argparse.ArgumentTypeError(msg)
    else:
        return dirname


def is_valid_gcf_id(arg, patt="GCF-\d{4}-\d{3}"):
    if arg is None:
        return True
    m = re.match(patt, arg)
    if m:
        return m.group().strip()
    else:
        msg = "{0} is not a valid GCF number (format: GCF-YYYY-NNN)".format(arg)
        raise argparse.ArgumentTypeError(msg)


def _match_project_dir(pth, project_id=None, test=False):
    """
    returns path and folder (project_id) of a project
    """
    if project_id:
        for fn in os.listdir(pth):
            if os.path.isdir(os.path.join(pth, fn)) and fn in project_id:
                return os.path.join(pth, fn), fn
        msg = "{0} is not present in run_folder: {1}".format(project_id, pth)
        logger.warning(msg)
        return None, None
    else:
        project_dir = None

        for fn in os.listdir(pth):
            if os.path.isdir(os.path.join(pth, fn)) and re.match("^GCF-\d{4}-\d{3}", fn):
                if project_dir is not None:
                    msg = "runfolders contain more than one project folders existing: {}, other: {}"
                    msg += "\nuse `--project-id` option to choose one."
                    logger.error(msg.format(project_id, fn))
                project_dir = os.path.join(pth, fn)
                project_id = fn
            elif test and re.match("GCF-\d{4}-\d{3}_samplesheet.tsv", fn):
                project_id = fn.split("_samplesheet.tsv")[0]
                project_dir = os.path.join(pth, project_id)
        if project_dir:
            logger.debug("project_dir match: {}".format(project_dir))
            return project_dir, project_id
        raise RuntimeError(
            "failed to identify any valid projects in runfolder: {}".format(pth)
        )



def get_data_from_samplesheet(fh):
    """Compatibility entry point using the shared validated SampleSheet parser."""
    result = ValidationResult()
    sheet = parse_samplesheet(fh.read(), getattr(fh, "name", "<stream>"), result)
    if not result.ok:
        raise InputValidationError(result)
    return (pd.DataFrame(sheet["records"])[sheet["columns"]], sheet["options"], sheet["header"])


def get_project_samples_from_samplesheet(args):
    result = getattr(args, "_validation", None)
    if result is None:
        result = validate_inputs(args.samplesheet, args.ssub, args.project_id, args.keep_batch)
    if not result.ok:
        raise InputValidationError(result)
    return result.samples.copy(), result.custom_options.copy(), result.header.copy()


def match_fastq(sample_name, project_dir, rel_path=True):
    """
    Return fastq files matching a sample name.

    Returns paths relative to project directory
    """
    r1_fastq_files, r2_fastq_files, i1_fastq_files = [], [], []
    for fn in os.listdir(project_dir):
        if fn == "{}_R1.fastq.gz".format(sample_name):
            r1_fastq_files.extend([os.path.join(project_dir, fn)])
        elif fn == "{}_R2.fastq.gz".format(sample_name):
            r2_fastq_files.extend([os.path.join(project_dir, fn)])
        elif fn == "{}_I1.fastq.gz".format(sample_name):
            i1_fastq_files.extend([os.path.join(project_dir, fn)])
        elif fn == sample_name:
            r1_fastq_files.extend(glob.glob(os.path.join(project_dir, sample_name, sample_name + "*_R1_001.fastq.gz")))
            r2_fastq_files.extend(glob.glob(os.path.join(project_dir, sample_name, sample_name + "*_R2_001.fastq.gz")))
            i1_fastq_files.extend(glob.glob(os.path.join(project_dir, sample_name, sample_name + "*_I1_001.fastq.gz")))
        elif re.match(sample_name + "_S\d+_L\d{3}_R1_001.fastq.gz", fn):
            r1_fastq_files.append(os.path.join(project_dir, os.path.basename(fn)))
        elif re.match(sample_name + "_S\d+_L\d{3}_R2_001.fastq.gz", fn):
            r2_fastq_files.append(os.path.join(project_dir, os.path.basename(fn)))
        elif re.match(sample_name + "_S\d+_L\d{3}_I1_001.fastq.gz", fn):
            i1_fastq_files.append(os.path.join(project_dir, os.path.basename(fn)))
        elif re.match(sample_name + "_S\d+_R1_001.fastq.gz", fn):
            r1_fastq_files.append(os.path.join(project_dir, os.path.basename(fn)))
        elif re.match(sample_name + "_S\d+_R2_001.fastq.gz", fn):
            r2_fastq_files.append(os.path.join(project_dir, os.path.basename(fn)))
        elif re.match(sample_name + "_S\d+_I1_001.fastq.gz", fn):
            i1_fastq_files.append(os.path.join(project_dir, os.path.basename(fn)))
            
    if (len(r1_fastq_files) == 0) and (len(r2_fastq_files) == 0):
        warn_msg = "Failed to match sample: {} with any fastq files in {}".format(sample_name, project_dir)
        logger.warning(warn_msg)
        return None, None, None
    
    r1_fastq_files = sorted(r1_fastq_files)
    r2_fastq_files = sorted(r2_fastq_files)
    i1_fastq_files = sorted(i1_fastq_files)
    if rel_path:
        upstream_pth = os.path.dirname(os.path.dirname(project_dir))
        r1_fastq_files = [os.path.relpath(x, upstream_pth) for x in r1_fastq_files]
        r2_fastq_files = [os.path.relpath(x, upstream_pth) for x in r2_fastq_files]
        i1_fastq_files = [os.path.relpath(x, upstream_pth) for x in i1_fastq_files]

    return r1_fastq_files, r2_fastq_files, i1_fastq_files


def find_samples(df, args):
    """
    identify valid samples by existing fastq file names
    """
    sample_dict = {}
    project_dirs = [os.path.join(run_folder, project_id) for run_folder, project_id in zip(args.runfolders, args.project_id)]
    for index, row in df.iterrows():
        s_r1, s_r2, s_i1 = [],[],[]
        fc_name, fc_id = [],[]
        for p_pth in project_dirs:
            flowcell_name = os.path.basename(os.path.split(p_pth)[0])
            flowcell_id = flowcell_name.split("_")[-1]
            r1, r2, i1 = match_fastq(row.Sample_ID, p_pth)
            if r1:
                s_r1.extend(r1)
                fc_name.extend([flowcell_name]*len(r1))
                fc_id.extend([flowcell_id]*len(r1))
            if r2:
                s_r2.extend(r2)
            if i1:
                s_i1.extend(i1)
        if all([i is None for i in s_r1]) and all([i is None for i in s_r2]):
            warn_str = "removing sample {} from SampleSheet due to missing fastq files!".format(row.Sample_ID)
            logger.warning(warn_str)
        else:
            if len(s_i1) > 0:
                sample = { "R1": ",".join(s_r1),
                           "R2": ",".join(s_r2),
                           "I1": ",".join(s_i1),
                           "Project_ID": ",".join(row.Project_ID),
                           "Sample_ID": row.Sample_ID,
                           "Flowcell_Name" : ",".join(fc_name),
                           "Flowcell_ID" : ",".join(fc_id)
                          }
            else:
                sample = {"R1": ",".join(s_r1),
                          "R2": ",".join(s_r2),
                          "Project_ID": ",".join(row.Project_ID),
                          "Sample_ID": row.Sample_ID,
                          "Flowcell_Name" : ",".join(fc_name),
                          "Flowcell_ID" : ",".join(fc_id)
                          }
            sample_dict[str(row.Sample_ID)] = sample
            
    return sample_dict


def find_samples_batch(df, args):
    """
    `find_samples` function adding Flowcell_ID postfix to Sample_ID
    """
    sample_dict = {}
    validation = getattr(args, "_validation", None)
    planned = {item["sample_id"]: item for item in validation.summary["planned_samples"]} if validation else None
    project_dirs = [os.path.join(run_folder, project_id) for run_folder, project_id in zip(args.runfolders, args.project_id)]
    for index, row in df.iterrows():
        for p_pth in project_dirs:
            r1, r2, i1 = match_fastq(row.Sample_ID, p_pth)
            if (not r1) and (not r2):
                warn_str = "sample {} not found in {}".format(row.Sample_ID, p_pth)
                logger.warning(warn_str)
            else:
                r2 = [] if not r2 else r2
                Flowcell_ID = Path(p_pth).parent.name.split("_")[-1]
                Sample_ID = "{}_{}".format(row.Sample_ID, Flowcell_ID)
                if planned is not None and Sample_ID not in planned:
                    continue
                project_ids = planned[Sample_ID]["project_ids"] if planned is not None else row.Project_ID
                if len(i1) > 0:
                    sample_dict[Sample_ID] = {
                        "R1": ",".join(r1),
                        "R2": ",".join(r2),
                        "I1": ",".join(i1),
                        "Project_ID": ",".join(project_ids),
                        "Sample_ID": Sample_ID,
                        "Src_Sample_ID": row.Sample_ID,
                        "Flowcell_Name": Path(p_pth).parent.name,
                        "Flowcell_ID": Flowcell_ID,
                    }
                else:
                    sample_dict[Sample_ID] = {
                        "R1": ",".join(r1),
                        "R2": ",".join(r2),
                        "Project_ID": ",".join(project_ids),
                        "Sample_ID": Sample_ID,
                        "Src_Sample_ID": row.Sample_ID,
                        "Flowcell_Name": Path(p_pth).parent.name,
                        "Flowcell_ID": Flowcell_ID,
                    }
    return sample_dict


def find_samples_test(df, args):
    sample_dict = {}
    validation = getattr(args, "_validation", None)
    planned = {item["sample_id"]: item for item in validation.summary["planned_samples"]} if validation else None
    for row in df.itertuples(index=False):
        batches = args.runfolders if args.keep_batch else [args.runfolders[0]]
        for runfolder in batches:
            flowcell = Path(runfolder).name
            sid = row.Sample_ID + "_" + flowcell.split("_")[-1] if args.keep_batch else row.Sample_ID
            if planned is not None and sid not in planned:
                continue
            project_ids = planned[sid]["project_ids"] if planned is not None else row.Project_ID
            sample_dict[sid] = {
                "R1": "{}_R1.fastq.gz".format(row.Sample_ID),
                "R2": "{}_R2.fastq.gz".format(row.Sample_ID),
                "Project_ID": ",".join(project_ids), "Sample_ID": sid,
                "Flowcell_Name": flowcell, "Flowcell_ID": flowcell.split("_")[-1],
            }
    return sample_dict


from configmaker.columns import _customer_column_mapper, _lab_column_mapper, _demux_column_mapper


def _validated_form(fn):
    result = ValidationResult()
    try:
        content = Path(fn).read_bytes()
    except OSError as error:
        result.add("error", "input.unreadable", str(error), file=str(fn))
        raise InputValidationError(result) from error
    form = parse_submission_form(content, str(fn), result)
    if not result.ok:
        raise InputValidationError(result)
    return form


def read_customer_sheet(fn):
    parsed = _validated_form(fn)["customer"]
    return parsed["data"], parsed["descriptors"]


def read_lab_sheet(fn):
    parsed = _validated_form(fn)["lab"]
    return parsed["data"], parsed["descriptors"]


def read_demux_sheet(fn):
    result = ValidationResult()
    form = parse_submission_form(Path(fn).read_bytes(), str(fn), result, require_demux=True)
    if not result.ok:
        raise InputValidationError(result)
    parsed = form["demux"]
    df = parsed["data"].copy()
    if "Wells" in df.columns:
        df["Wells"] = df["Wells"].map(lambda value: str(value).replace(" ", "") if not pd.isna(value) else value)
    return df, parsed["descriptors"]


def sample_submission_form_parser(ssub_path, keep_batch=None):
    """Compatibility wrapper; normal initialization reuses its preflight result."""
    form = _validated_form(ssub_path)
    frame = form["data"].copy()
    if keep_batch:
        frame["Sample_ID"] += "_" + Path(ssub_path).parent.name.split("_")[-1]
    frame.index = frame["Sample_ID"]
    return frame, form["descriptors"]


def merge_samples_with_submission_form(sample_dict, args):
    """
    """
    result = getattr(args, "_validation", None)
    if result is None:
        result = validate_inputs(args.samplesheet, args.ssub, args.project_id, args.keep_batch)
    if not result.ok:
        raise InputValidationError(result)
    merge = result.metadata.copy()
    desc = copy.deepcopy(result.descriptors)
    check_existence_of_samples(sample_dict.keys(), merge)
    sample_df = pd.DataFrame.from_dict(sample_dict, orient="index")
    if "Project_ID" in sample_df.columns and "Project_ID" in merge:
        # use Project_ID from samplesheet over sample-submission-form
        merge = merge.drop("Project_ID", axis=1)
    sample_df = sample_df.merge(merge.reset_index(drop=True), on="Sample_ID", how="left", validate="one_to_one")
    sample_df.reset_index()
    sample_df.index = sample_df["Sample_ID"]

    if args.new_project_id:
        sample_df = sample_df.rename(columns={"Project_ID": "Src_Project_ID"})
        sample_df["Project_ID"] = args.new_project_id

    desc = descriptors.descriptors.add_default_descriptors(sample_df, desc)
    # Descriptor inference sanitizes strings, including IDs; identity fields
    # must retain exactly the values already accepted by metadata preflight.
    identities = sample_df[[c for c in ("Sample_ID", "Project_ID", "Src_Project_ID") if c in sample_df]].copy()
    sample_df, desc = descriptors.descriptors.infer_by_descriptor(sample_df, desc)
    for column in identities:
        sample_df[column] = identities[column]
    sample_df.index = sample_df["Sample_ID"]
    if "Organism" in sample_df.columns:
        if len(set(sample_df.Organism.values)) == 1:  # single customer org
            if args.organism is not None:
                sample_df["Organism"] = args.organism
            else:
                # if org is N/A in samplesheet but single org in sample_df
                #args.organism = list(sample_df.Organism)[0]
                customer_org = list(sample_df.Organism)[0]
                logger.warning("Organism is N/A in samplesheet with customer Organsim columns has one value: {}\n....keeping N/A".format(customer_org))
                
    return sample_df, desc


def check_existence_of_samples(samples, df):
    diff = list(set(samples) - set(df["Sample_ID"].astype(str)))
    if diff:
        extra = ""
        n_diff = len(diff)
        if n_diff > 10:
            diff = diff[:10]
            extra = ",... +{} samples".format(n_diff - 10)
        vals = ",".join(list(diff)) + extra
        msg = "Samples {} are contained in SampleSheet, but not in sample submission form. Sample info from these samples will have empty values."
        logger.error(msg.format(vals))
        raise ValueError

    diff2 = list(set(df["Sample_ID"].astype(str)) - set(samples))
    if diff2:
        extra = ""
        n_diff2 = len(diff2)
        if n_diff2 > 10:
            diff2 = diff2[:10]
            extra = ",... +{} samples".format(n_diff2 - 10)
        vals2 = ",".join(list(diff2)) + extra
        msg = "Samples {} are contained in sample submission form, but not in SampleSheet. Sample info from these samples are omitted."
        logger.info(msg.format(vals2))
    return None


def find_machine(runfolders):
    n_matches = set()
    for pth in runfolders:
        machine_code = os.path.basename(pth).split("_")[1]
        machine = SEQUENCERS.get(machine_code, "")
        n_matches.add(machine)
    if len(n_matches) > 1:
        # logger.warning('Multiple sequencing machines identified!')
        raise ValueError("Multiple sequencing machines identified!")
    return machine

def find_fastq_md5sums(runfolders, project_id):
    df_list = []
    fn_list = []
    for pth in runfolders:
        for pid in project_id:
            fn = os.path.join(pth, 'md5sum_{}_fastq.txt'.format(pid))
            fn_list.append(fn)
            if os.path.isfile(fn):
                df = pd.read_table(fn, header=None, sep="\s+", names=['md5sum', 'filename'])
                df['filename'] = df['filename'].apply(lambda x: os.path.split(x)[-1])
                df = df.set_index('filename')
                df_list.append(df)

    if len(df_list) == 1:
        return df_list[0].to_dict()['md5sum']
    elif len(df_list) > 1:
        return pd.concat(df_list).to_dict()['md5sum']
    else:
        logger.warning("None of {} was not found".format(', '.join(fn_list)))
        return None

def create_default_config(merged_samples, opts, args, fastq_dir=None, descriptors=None, write_yaml=False, md5sums=None):
    """
    create configuration dictionary
    """
    samples = merged_samples.to_dict(orient="index")
    config = {}
    if len(set(args.project_id)) == 1:
        args.project_id = [args.project_id[0]]

    if args.new_project_id:
        config["project_id"] = args.new_project_id
        config["src_project_id"] = args.project_id
    else:
        config["project_id"] = copy.deepcopy(args.project_id)

    if args.organism is not None:
        if pd.isnull(args.organism) or args.organism in ["N/A", "NA", "<NA>", "", None]:
            config["organism"] = "N/A"
        else:
            config["organism"] = args.organism

    if args.subsample:
        config["filter"] = {"subsample_fastq": args.subsample}
    else:
        config["filter"] = {"subsample_fastq": "skip"}

    if "Libprep" in opts:
        config["libprepkit"] = opts["Libprep"]
    if args.libkit is not None:
        config["libprepkit"] = args.libkit

    config["read_geometry"] = find_read_geometry(args.runfolders)
    config["machine"] = args.machine or find_machine(args.runfolders)

    if args.PI is not None:
        config["experiment_principal_inverstigator"] = args.PI
    if args.contributor is not None:
        config["experiment_contributor"] = args.contributor
    if args.title is not None:
        config["experiment_title"] = args.title
    else:
        config["experiment_title"] = config["project_id"]
    if args.summary is not None:
        config["experiment_summary"] = args.summary
    batch = {}
    if args.keep_batch:
        batch["name"] = "Flowcell_ID"
        config['multiple_flowcells'] = False
    else:
        batch["method"] = "skip"
        if any(merged_samples.Flowcell_ID.str.contains(',')):
            config['multiple_flowcells'] = True
        else:
            config['multiple_flowcells'] = False
    
    quant = {"batch": batch}
    config["quant"] = quant

    if fastq_dir:
        config["fastq_dir"] = fastq_dir

    if descriptors:
        current_col_names = set()
        for k, v in samples.items():
            for n in v.keys():
                current_col_names.add(n)
        keys = current_col_names.intersection(descriptors.keys())
        config["descriptors"] = {}
        for k in keys:
            if k in descriptors:
                if descriptors[k]:
                    config["descriptors"][k] = descriptors[k]

    config["samples"] = {}
    for sample_id, col in samples.items():
        config["samples"][sample_id] = {}
        for col_name, val in col.items():
            if isinstance(val, Iterable) and not isinstance(val, six.string_types):
                #stringify if list
                val = list(map(str, val))
            else:
                val = str(val)
            config["samples"][sample_id][col_name] = val

            if col_name in ["R1", "R2", "I1"] and md5sums is not None:
                md5 = [md5sums.get(os.path.basename(i)) for i in val.split(',')]
                if md5 and val:
                    config["samples"][sample_id][col_name+ "_md5sum"] = ','.join(md5) 

    if opts.get("Libprep",'').startswith("Parse Biosciences"):
        demux_df, demux_desc = read_demux_sheet(args.ssub[0])

        config['wells'] = {}
        for k,v in demux_df.to_dict(orient="index").items():
            config['wells'][v['Sample_ID']] = v

    if write_yaml:
        yaml.safe_dump(config, args.output)

    return config


def create_fastq_dir(sample_dict, args, output_dir=None, overwrite=True):
    """
    Symlink fastq files into project specific names and destinations
    """
    if args.skip_create_fastq_dir:
        return None
    default_fastq_dir = output_dir or os.path.join("data", "raw", "fastq")
    if os.path.exists(default_fastq_dir) and overwrite:
        shutil.rmtree(default_fastq_dir)
    os.makedirs(default_fastq_dir, exist_ok=True)

    s_ids = sample_dict.keys()
    if args.keep_batch:
        # split out date addition postfix from sample_ids with support for sample_ids with underscore in name
        s_ids = ["_".join(n[:-1]) if len(n) > 2 else n[0] for n in [e.split("_") for e in s_ids]]
        s_ids = list(set(s_ids))  # unique sample_ids

    project_dirs = [os.path.join(run_folder, project_id) for run_folder, project_id in zip(args.runfolders, args.project_id)]
    for sample_id in s_ids:
        for pid in project_dirs:
            r1_src, r2_src, i1_src = match_fastq(sample_id, pid, rel_path=False)
            r1_dst, r2_dst, i1_dst = match_fastq(sample_id, pid, rel_path=True)
            if not any([r1_src, r1_dst, r2_src, r2_dst]):
                continue
            for src, dst in zip(r1_src, r1_dst):
                if src is not None:
                    dst = os.path.join(default_fastq_dir, dst)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.symlink(src, dst)
            for src, dst in zip(r2_src, r2_dst):
                if src is not None:
                    dst = os.path.join(default_fastq_dir, dst)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.symlink(src, dst)
            for src, dst in zip(i1_src, i1_dst):
                if src is not None:
                    dst = os.path.join(default_fastq_dir, dst)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.symlink(src, dst)    
    return default_fastq_dir




def _merge_defaults(config, defaults):
    """Fill missing nested kit settings while retaining explicit project options."""
    for key, value in defaults.items():
        if key not in config:
            config[key] = copy.deepcopy(value)
        elif isinstance(config[key], dict) and isinstance(value, dict):
            _merge_defaults(config[key], value)


def add_workflow(config, src_dir=None, *, libprep_config=None,
                 expected_sha256=None, expected_entry=None, expected_read_geometry=None):
    """Select a kit from one snapshot; standalone sources remain portable."""
    wf_path = Path(src_dir or "src") / "gcf-workflows"
    if not wf_path.exists():
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", GCF_WORKFLOWS_SRC, str(wf_path)])

    snapshot = (libprep_config if isinstance(libprep_config, LibprepConfig)
                else LibprepConfig.load(libprep_config or wf_path / "libprep.config"))
    if expected_sha256 is not None and snapshot.sha256 != expected_sha256:
        raise LibprepConfigError("Libprep configuration hash mismatch for {}: expected {}, got {}".format(
            snapshot.source, expected_sha256, snapshot.sha256))
    selection = snapshot.select(config.get("libprepkit"), config["read_geometry"])
    if expected_entry is not None and selection.entry != expected_entry:
        raise LibprepConfigError("Libprep entry mismatch: expected {!r}, got {!r}".format(expected_entry, selection.entry))
    if expected_read_geometry is not None and tuple(expected_read_geometry) != selection.read_geometry:
        raise LibprepConfigError("Read geometry changed since BFQ selection: expected {}, got {}".format(
            expected_read_geometry, selection.read_geometry))
    if config.get("workflow", selection.workflow) != selection.workflow:
        raise LibprepConfigError("Configured workflow conflicts with selected libprep entry {!r}".format(selection.entry))

    _merge_defaults(config, selection.parameters)
    config["libprep_selection"] = selection.diagnostics()
    logger.warning("Libprep selection: %s", json.dumps(selection.diagnostics(), sort_keys=True))
    snapshot.write(wf_path / "libprep.config")
    with open("Snakefile", "w") as sn:
        sn.write(SNAKEFILE_TEMPLATE.format(workflow=selection.workflow))
    return config

def project_summary(config, output="config.yaml", validation=None):
    """Persist analysis-time FASTQ discovery, separate from metadata preflight."""
    samples = []
    for sid, info in config["samples"].items():
        flowcells = sorted(set(filter(None, info.get("Flowcell_Name", "").split(","))))
        samples.append({"sample_id": sid, "flowcells": flowcells})
    planned = {item["sample_id"] for item in validation.summary["planned_samples"]} if validation else set(config["samples"])
    report = {"schema_version": 1, "kind": "fastq_discovery", "samples": samples,
              "sample_count": len(samples), "planned_sample_count": len(planned),
              "missing_sample_ids": sorted(planned - set(config["samples"]))}
    directory = Path(output).parent
    summary_file = directory / "configmaker.analysis-summary.json"
    summary_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = ["FASTQ discovery: {} of {} planned sample(s) found.".format(len(samples), len(planned))]
    lines.extend("Sample {} found in: {}".format(item["sample_id"], ", ".join(item["flowcells"])) for item in samples)
    if report["missing_sample_ids"]:
        lines.append("No FASTQs found for: " + ", ".join(report["missing_sample_ids"]))
    (directory / ".configmaker.log").write_text("\n".join(lines) + "\n")
    print(lines[0])
    print("FASTQ discovery summary written to {}".format(summary_file))
    return report


def check_input(args):
    logger.debug("running check_input ...")
    dirs, ids, samplesheets, submission_forms = [], [], [], []
    for pth in args.runfolders:
        project_dir, project_id = _match_project_dir(pth, project_id=args.project_id, test=args.test)
        if project_id:
            dirs.append(project_dir)
            ids.append(project_id)
            samplesheet_fn = os.path.join(pth, "SampleSheet.csv")
            ssub_fn = os.path.join(pth, "Sample-Submission-Form.xlsx")
            if os.path.exists(samplesheet_fn) and args.samplesheet is None:
                logger.debug("identified samplesheet: {}".format(samplesheet_fn))
                samplesheets.append(samplesheet_fn)
            if os.path.exists(ssub_fn) and args.ssub is None:
                logger.debug("identified submission form: {}".format(ssub_fn))
                submission_forms.append(ssub_fn)

    if args.samplesheet is not None:
        logger.debug("overriding samplesheet with command line arg: {}".format(args.samplesheet))
        args.samplesheet = [str(args.samplesheet)]
    else:
        if len(samplesheets) == 0:
            msg = "cannot find SampleSheet.csv in runfolders. Use --samplesheet for manual override"
            logger.error(msg)
            raise RuntimeError(msg)
        args.samplesheet = samplesheets
    if args.ssub is not None:
        args.ssub = [str(args.ssub)]
    else:
        if len(submission_forms) == 0:
            msg = "cannot find Sample-Submission-Form.xlsx in runfolders. Use --submission-form for manual override"
            logger.error(msg)
            raise RuntimeError(msg)
        args.ssub = submission_forms
    args.project_id = ids
    args.runfolders = [os.path.dirname(p) for p in dirs]

    #args.organism = descriptors.fuzzmatch.fuzzmatch_organism(args.organism)

    return args

def check_organism_and_reference_db(config):
    import reference_db
    org = str(config.get('organism', '')).strip().replace(" ", "_")
    config['organism'] = reference_db.check_organism()
    return config


def subsample_input_type(arg):
    if not arg:
        return None
    try:
        s = float(arg)
    except ValueError:
        raise argparse.ArgumentTypeError("Subsample must be a number")
    if s <= 0:
        raise argparse.ArgumentTypeError("Subsample must be > 0")
    elif s == 1:
        s = None
    elif s > 1:
        s = int(s)
    return s


def parse_args(argv=None):
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-p", "--project-id",
                        nargs="+",
                        help="Project ID",
                        default=None,
                        type=is_valid_gcf_id
                        )
    parser.add_argument("-P","--new-project-id",
                        help="New Project ID",
                        default=None,
                        type=is_valid_gcf_id,
                        )
    parser.add_argument("runfolders",
                        nargs="+",
                        help="Path(s) to flowcell dir(s)",
                        action=FullPaths,
                        type=is_dir,
                        )
    parser.add_argument("-s", "--sample-sheet",
                        dest="samplesheet",
                        type=Path,
                        help="IEM Samplesheet",
                        )
    parser.add_argument("-o","--output",
                        default="config.yaml",
                        help="Output config file",
                        type=Path,
                        )
    parser.add_argument("-S","--sample-submission-form",
                        dest="ssub",
                        type=Path,
                        help="GCF Sample Submission Form",
                        )
    parser.add_argument("--subsample",
                        type=subsample_input_type,
                        default=None,
                        help="Subsample fastq. Float between 0 and 1 for fraction, int > 1 for number of reads.",
                        )
    parser.add_argument("--organism",
                        help="Organism (if applicable to all samples). Overrides value from samplesheet.",
                        )
    parser.add_argument("--libkit",
                        help="Library preparation kit name. (if applicable for all samples). Overrides value from samplesheet."
                        )
    parser.add_argument("--libprep-config", type=Path,
                        help="Explicit configuration snapshot (default: src/gcf-workflows/libprep.config)")
    parser.add_argument("--libprep-sha256", help="Require this configuration SHA-256")
    parser.add_argument("--libprep-entry", help="Require this exact selected entry")
    parser.add_argument("--expected-read-geometry", nargs="+", type=int,
                        help="Require these read lengths from Stats.json")
    parser.add_argument("--machine",
                        help="Sequencer model."
                        )
    parser.add_argument("--PI",
                        default = "NA",
                        help="Name of Principal Inverstigator (data deposition)"
                        )
    parser.add_argument("--contributor",
                        default = None,
                        help="Name of acting inverstigator (data deposition)"
                        )
    parser.add_argument("--title",
                        default = None,
                        help="Experiment title (data deposition)"
                        )
    parser.add_argument("--summary",
                        default = "NA",
                        help="Experiment summary (data deposition)"
                        )
    parser.add_argument("--skip-create-fastq-dir",
                        action="store_true",
                        help="Skip creation of fastq dir and symlink fastq files",
                        )
    parser.add_argument("--skip-peppy",
                        action="store_true",
                        help="Skip creation of a peppy project"
                        )
    parser.add_argument("--keep-batch",
                        action="store_true",
                        help="Sample names will be made unique for each batch.",
                        )
    parser.add_argument("--verbose",
                        action="store_true", help="Verbose output"
                        )
    parser.add_argument("--test",
                        action="store_true",
                        help="Activate test-mode. (no fastq files needed)",
                        )

    parser.add_argument("--expected-validation-version", help="Require this shared validator version before initializing output")
    args = parser.parse_args(argv)
    return args


def main(argv=None):
    args = parse_args(argv)
    setup_logger(args.verbose)
    try:
        if args.expected_validation_version and args.expected_validation_version != VALIDATOR_VERSION:
            raise ValueError("Shared validator version mismatch: expected {}, installed {}. Install matching gcf-tools in the BFQ and configmaker environments.".format(args.expected_validation_version, VALIDATOR_VERSION))
        args = check_input(args)
        validation = validate_inputs(args.samplesheet, args.ssub, args.project_id, args.keep_batch)
        print(validation.render_text(), file=sys.stdout if validation.ok else sys.stderr)
        if not validation.ok:
            return 2
        args._validation = validation
        samples_df, custom_opts, header = get_project_samples_from_samplesheet(args)
        args.organism = args.organism or custom_opts.get("Organism")
        args.organism = args.organism or descriptors.fuzzmatch.fuzzmatch_organism(args.organism)
        if args.test:
            sample_dict = find_samples_test(samples_df, args)
        elif args.keep_batch:
            sample_dict = find_samples_batch(samples_df, args)
        else:
            sample_dict = find_samples(samples_df, args)
        if not sample_dict:
            raise ValueError("FASTQ discovery failed: no matching FASTQs were found for {} planned sample(s). Check runfolders, project directories and Sample_ID spelling. Metadata preflight passed.".format(validation.summary["planned_sample_count"]))
        merged_samples, desc = merge_samples_with_submission_form(sample_dict, args)
        fastq_dir = create_fastq_dir(sample_dict, args)
        md5sums = find_fastq_md5sums(args.runfolders, args.project_id)
        config = create_default_config(merged_samples, custom_opts, args, fastq_dir=fastq_dir, descriptors=desc, md5sums=md5sums)
        config = add_workflow(config, libprep_config=args.libprep_config,
                              expected_sha256=args.libprep_sha256,
                              expected_entry=args.libprep_entry,
                              expected_read_geometry=args.expected_read_geometry)
        with open(args.output, "w") as output:
            yaml.safe_dump(config, output)
        if not args.skip_peppy:
            import peppy_support
            peppy_support.create_peppy(config, output_dir="pep")
        project_summary(config, args.output, validation)
        return 0
    except (InputValidationError, LibprepConfigError, OSError, RuntimeError, ValueError) as error:
        logger.error("%s", error)
        return 2


if __name__ == "__main__":
    sys.exit(main())
