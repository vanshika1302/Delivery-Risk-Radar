"""Run the pipeline steps in order: extract, load, transform (scope, stages, labels).

    python -m etl.run_pipeline                 # extract (skipped if already complete) and load
    python -m etl.run_pipeline --skip-extract  # only reload DuckDB from existing Parquet
"""
from __future__ import annotations

import argparse
from pathlib import Path

from etl import extract, load, transform


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--skip-extract", action="store_true")
    p.add_argument("--force", action="store_true", help="redo the extraction even if one is complete")
    p.add_argument("--connections", type=int, default=16)
    a = p.parse_args(argv)
    if not a.skip_extract:
        extract.run(force=a.force, connections=a.connections)
    load.main([])
    transform.main([])


if __name__ == "__main__":
    main()
