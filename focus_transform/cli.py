"""
Standalone CLI for running the transform locally - useful for testing
against a real (or sample) FOCUS CSV before wiring anything up to Azure.

Examples:
    # Transform a local file and write outputs to a local folder (no upload)
    python -m focus_transform.cli --input focus_export.csv --output-dir ./out

    # Transform and upload to the real destination container
    python -m focus_transform.cli --input focus_export.csv --upload
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import ConfigError, Settings
from .manifest import build_manifest, derive_report_period
from .schema import validate_focus_columns
from .storage import upload_outputs
from .transform import clean_billing_account_id, csv_to_parquet, load_focus_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("focus_transform.cli")


def run(input_path: Path, output_dir: Path | None, upload: bool) -> int:
    csv_bytes = input_path.read_bytes()

    df = load_focus_csv(csv_bytes)
    validate_focus_columns(df)  # logs warnings only, doesn't block
    df = clean_billing_account_id(df)
    parquet_bytes = csv_to_parquet(df)

    report_period = derive_report_period(df)

    if upload:
        try:
            settings = Settings.from_env()
        except ConfigError as exc:
            logger.error(str(exc))
            return 1

        paths, manifest = build_manifest(
            report_period, settings.vendor, settings.optional_sub_directories
        )
        upload_outputs(
            settings.dest_account_url,
            settings.dest_container,
            parquet_bytes,
            manifest,
            paths,
        )
        logger.info("Upload complete.")
        return 0

    # Local dry run - write outputs to disk instead of uploading
    if output_dir is None:
        output_dir = Path("./focus_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    paths, manifest = build_manifest(report_period, vendor="Azure")
    parquet_path = output_dir / paths["parquet_filename"]
    manifest_path = output_dir / paths["manifest_filename"]

    parquet_path.write_bytes(parquet_bytes)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    logger.info("Dry run complete. Would upload to: %s", paths["base_path"])
    logger.info("Local outputs written: %s, %s", parquet_path, manifest_path)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FOCUS transform locally.")
    parser.add_argument("--input", required=True, type=Path, help="Path to the FOCUS CSV file")
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Where to write Parquet + manifest for a local dry run (default: ./focus_output)",
    )
    parser.add_argument(
        "--upload", action="store_true",
        help="Upload to the real destination container instead of a local dry run "
             "(requires FOCUS_DEST_ACCOUNT_URL and FOCUS_DEST_CONTAINER env vars)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    sys.exit(run(args.input, args.output_dir, args.upload))


if __name__ == "__main__":
    main()
