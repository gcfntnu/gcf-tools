#!/usr/bin/env python
"""Create testdata suitable to run bfq pipelines by subsampling an existing bfq output folder.
"""
import sys
import os
import collections
import argparse
import warnings
import subprocess
import logging
import glob
import re
import random
import shutil
from urllib.request import urlopen

import pandas as pd
import yaml

libprepconf_url = "https://raw.githubusercontent.com/gcfntnu/gcf-workflows/main/libprep.config"


def load_libprep_config(filename=None):
    """Read an explicit local source, otherwise retain the historical remote source.

    Explicit files never fall back to the network. Unlike the old wget boundary,
    the implicit download does not create/remove a configuration file in cwd.
    """
    if filename is not None:
        with open(filename, "rb") as handle:
            config = yaml.safe_load(handle)
    else:
        with urlopen(libprepconf_url, timeout=30) as handle:
            config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Libprep configuration must be a YAML mapping")
    return config


def require_tool(name):
    path = shutil.which(name)
    if path is None:
        raise RuntimeError("Required producer executable {!r} is missing from PATH; "
                           "see docs/testdata.md for the tested tool baseline".format(name))
    return path


def sample_fastq(source, destination, n_reads):
    """Run the historical per-file sampling pipeline without shell interpolation.

    Return both exit statuses for inspection. The legacy caller still ignores
    them; propagation and paired validation are explicitly deferred to #64.
    """
    gzip = require_tool("gzip")
    seqkit = require_tool("seqkit")
    with open(destination, "wb") as output:
        with subprocess.Popen([gzip, "-cd", "--", source], stdout=subprocess.PIPE) as reader:
            try:
                result = subprocess.call([seqkit, "sample", "-n", str(n_reads), "-s", "123456"],
                                         stdin=reader.stdout, stdout=output)
            finally:
                reader.stdout.close()
            return reader.wait(), result


def compress_fastqs(directory, nested=False):
    """Retain the old one-level glob and gzip behavior, exposing its exit status."""
    pattern = "*/*" if nested else "*"
    filenames = sorted(glob.glob(os.path.join(directory, pattern)))
    if not filenames:
        return 0
    return subprocess.call([require_tool("gzip"), "--", *filenames])

def sample_samplesheet(input_fn, output_fn, samples, valid_samples):
    """Subset SampleSheet.csv 

    Subset by extracting lines under [Data] corresponding to samples.
    
    Parameters
    ----------
    input_fn : str
        Input filename
    output_fn : str
        Output filename
    samples : list-like
        List of sample-ids for subsetting
    valid_samples : list-like
        List of valid sample-ids
    
    """
    output = []
    remove_samples = set(valid_samples).difference(samples)
    with open(input_fn) as fh:
        for i, line in enumerate(fh):
            if line.startswith('[Data]'):
                header = fh.readline().strip('\n').split(',')
                sample_id_index = header.index('Sample_ID')
                header_line = i +1
    with open(input_fn) as fh:
        lines = fh.read().splitlines()
        for i, line in enumerate(lines):
            els = line.split(',')
            if i > header_line and els[sample_id_index] in remove_samples:
                pass
            else:
               output.append(line)
    with open(output_fn, 'w') as fh:
        for line in output:
            fh.write(line + '\n')


class BFQoutput():
    """Class representing a bfq-pipeline output directory

    Attributes
    ----------
    dirname : str 
       path to bfq-pipeline output directory
    pipeline : str 
       name of gcf-pipeline, can be None
    fastq_files : dict
       samples to fastq file mapping
 
    """
    def __init__(self, dirname=None, libprep_config=None):
        self.dirname = dirname
        self.libprep_config = libprep_config
        self.pipeline = None
        self.fastq_files = None
        self._archive = None
        self._gcf_number = None
        self._fastq_dir = None

        self._inspect()

    def _inspect(self):
        """Validate bfq output directory
        """
        if not os.path.exists(self.dirname):
            raise ValueError('BFQ output dir does not exist')

        samplesheet = os.path.join(self.dirname, 'SampleSheet.csv')
        with open(samplesheet) as fh:
            for line in fh.read().splitlines():
                if line.startswith('ExperimentName'):
                    self._gcf_number = line.split(',')[1]
                    logging.info("identifed gcf number from samplesheet: {}".format(self._gcf_number))
                if line.startswith('Libprep'):
                    libprep = line.split(',')[1]
                    libconf_d = load_libprep_config(self.libprep_config)
                    if libprep + " SE" in libconf_d.keys():
                        self.pipeline = libconf_d[libprep + ' SE']['workflow']
                    elif libprep + " PE" in libconf_d.keys():
                        self.pipeline = libconf_d[libprep + ' PE']['workflow']
                    else:
                        warnings.warn('failed to identify pipeline from libprep name, using default workflow')
                        self.pipeline = "default"
                    logging.info("identifed library prep kit from samplesheet: {}".format(libprep))
                    logging.info("pipeline: {}".format(self.pipeline))
                    break
        self._fastq_dir = os.path.join(self.dirname, self._gcf_number)
        if not os.path.exists(self._fastq_dir):
            raise ValueError('Missing fastq dir. Expected {}'.format(self._fastq_dir)) 

        df = pd.read_csv(os.path.join(self.dirname, '{}_samplesheet.tsv'.format(self._gcf_number)), sep='\t')
        self.fastq_files = {}
        for sample in df.Sample_ID:
            samples = [s.split(self._fastq_dir + "/")[-1] for s in glob.glob(os.path.join(self._fastq_dir, "**", "{}*.fastq.gz".format(sample)), recursive=True)]
            self.fastq_files[sample] = samples

    def sample(self, output_dir, overwrite=True, n_reads=10000, n_samples=3, samples=None, no_fastq_rename=False):
        """Main subsampling routine.
        This method subsamples and writes output files.

        Params
        ------
        output_dir : str, path-like
        overwrite : boolean
            Force overwriting of existing output directory
        n_reads : int
            Number of random subsampled reads for each fastq file
        n_samples : int
            Number of random subsampled samples. This will be ignored if `samples` is not None
        samples : list
            List of sample-ids to use in sampling
        no_fastq_rename: boolean
            Keep original fastq naming scheme
        """
        logging.info("start copy of files from bfq output to : {}".format(output_dir))
        if os.path.exists(output_dir):
            if overwrite:
                shutil.rmtree(output_dir)
            else:
                raise ValueError('Output dir already exists.')
        os.makedirs(output_dir, exist_ok=False)
        dirs = ['Stats', 'InterOp']
        files = ['bcl.done', 'Sample-Submission-Form.xlsx']
        os.makedirs(output_dir, exist_ok=True)
        for direc in dirs:
            src = os.path.join(self.dirname, direc)
            dst = os.path.join(output_dir, direc)
            logging.info("copy tree: {} -> {}".format(src, dst))
            shutil.copytree(src, dst)
        for fn in files:
            src = os.path.join(self.dirname, fn)
            dst = os.path.join(output_dir, fn)
            logging.info("copy file: {} -> {}".format(src, dst))
            shutil.copy(src, dst)

        # susbet and copy fastq files
        fastq_dir_output = os.path.join(output_dir, os.path.basename(self._fastq_dir))
        os.makedirs(fastq_dir_output, exist_ok=True)
        if samples is None:
            SAMPLES = list(self.fastq_files.keys())
            SAMPLES = random.choices(SAMPLES, k=n_samples)
        else:
            SAMPLES = [i.strip() for i in samples.split(',')]
            for i in SAMPLES:
                if i not in self.fastq_files.keys():
                    logging.warning('sample {} is not a vaid sample id'.format(i))
                    logging.warning('valid samples: {}'.format(str(self.fastq_files.keys())))
                    raise AssertionError
        for sample in SAMPLES:
            fq_files = self.fastq_files[sample]
            for fq_basename in fq_files:
                src = os.path.join(self._fastq_dir, fq_basename)
                if self.pipeline == 'singlecell' or no_fastq_rename:
                    dst = os.path.join(fastq_dir_output, fq_basename).replace(".fastq.gz",".fastq")
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                else:
                    read_num = 'R1' if fq_basename.endswith('_R1.fastq.gz') else 'R2'
                    new_basename = '{}_S1_{}_001.fastq'.format(sample, read_num)
                    dst = os.path.join(fastq_dir_output, new_basename)
                sample_fastq(src, dst, n_reads)
        # gzip fastq files        
        logging.info('compressing fastq files ....')
        compress_fastqs(fastq_dir_output, nested=self.pipeline == 'singlecell')

        # subsample samplesheet
        logging.info('subsampling SampleSheet.csv ... ')
        src = os.path.join(self.dirname, 'SampleSheet.csv')
        dst = os.path.join(output_dir, 'SampleSheet.csv')
        sample_samplesheet(src, dst, samples=SAMPLES, valid_samples=list(self.fastq_files.keys()))

def create_argparser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("runfolder", help="path to flowcell dir")
    parser.add_argument("--output", help="output dir")
    parser.add_argument("--n-reads", default=1000, type=int, help="number of reads. (random subset)")
    parser.add_argument("--n-samples", default=3, type=int, help="number of samples (random subset)")
    parser.add_argument("--samples", help="comma separated list of sample ids to subset. This will overrride `--n-samples`")
    parser.add_argument("--no-fastq-rename", action='store_true', help="keep bfq fastq renaming scheme")
    parser.add_argument("--libprep-config", help="explicit local libprep YAML; overrides the historical remote default")
    parser.add_argument("--verbose", action='store_true')
    
    return parser


def main(argv=None):
    parser = create_argparser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level='INFO', format='[%(levelname)s] %(message)s')

    try:
        bfq = BFQoutput(args.runfolder, libprep_config=args.libprep_config)
        bfq.sample(args.output, n_reads=args.n_reads, n_samples=args.n_samples, samples=args.samples, no_fastq_rename=args.no_fastq_rename)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as error:
        parser.exit(1, "Testdata producer failed: {}\n".format(error))


if __name__ == "__main__":
    main()
