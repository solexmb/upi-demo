"""
Unattended, end-to-end daily pipeline: finds the latest Cost Management
Export in the source container, transforms it, and uploads the result to
the destination container Cloudability watches.

This is the entry point for a scheduled runner (GitLab CI, cron, Azure
Automation, etc.) - unlike cli.py, it takes no file path argument. It
decides for itself which file is "today's" export by picking the
most-recently-modified matching blob in the source container.

Usage:
    python -m focus_transform.pipeline

Required environment variables:
    SOURCE_ACCOUNT_URL, SOURCE_CONTAINER   - where the Cost Management Export lands
    FOCUS_DEST_ACCOUNT_URL, FOCUS_DEST_CONTAINER - where Cloudability reads from

Optional:
    SOURCE_PREFIX, FOCUS_VENDOR, FOCUS_SUB_DIRECTORIES,
    FOCUS_REPORT_PREFIX, FOCUS_SPEC_VERSION

Authentication: uses DefaultAzureCredential, same as the rest of the
package. In GitLab CI, set AZURE_CLIENT_ID, AZURE_TENANT_ID, and
AZURE_CLIENT_SECRET as masked/protected CI/CD variables for a service
principal that has Storage Blob Data Reader on the source container and
Storage Blob Data Contributor on the destination container -
DefaultAzureCredential picks these three up automatically, no code change
needed to switch between running locally and running in CI.
"""

from __future__ import annotations

import logging
import sys

import pandas as pd

from .config import ConfigError, Settings
from .manifest import build_manifest, derive_report_period
from .schema import validate_focus_columns
from .storage import download_blob, get_latest_blob_per_prefix, upload_outputs
from .transform import clean_billing_account_id, csv_to_parquet, load_focus_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("focus_transform.pipeline")


def run() -> int:
    try:
        settings = Settings.from_env()
        settings.require_source()
    except ConfigError as exc:
        logger.error(str(exc))
        return 1

    try:
        logger.info(
            "Looking for the latest export in container=%s (prefixes=%r)",
            settings.source_container, settings.source_prefixes,
        )
        blob_names = get_latest_blob_per_prefix(
            settings.source_account_url, settings.source_container, settings.source_prefixes
        )

        frames = []
        for blob_name in blob_names:
            csv_bytes = download_blob(settings.source_account_url, settings.source_container, blob_name)
            frames.append(load_focus_csv(csv_bytes))

        periods = {derive_report_period(f) for f in frames}
        if len(periods) > 1:
            raise RuntimeError(f"Exports span different report periods: {sorted(periods)}")

        df = pd.concat(frames, ignore_index=True)
        validate_focus_columns(df)  # logs a warning if columns are missing, doesn't block
        df = clean_billing_account_id(df)

        # Make a wrong result visible in the job log instead of only in the parquet.
        logger.info(
            "Combined %d export file(s): rows per file=%s, total=%d",
            len(frames), [len(f) for f in frames], len(df),
        )
        if "SubAccountId" in df.columns:
            logger.info("Rows per SubAccountId: %s", df["SubAccountId"].value_counts().to_dict())
        if "BillingAccountId" in df.columns:
            leftover = int(df["BillingAccountId"].astype(str).str.startswith("/providers/").sum())
            if leftover:
                logger.warning("%d rows still have an un-cleaned BillingAccountId", leftover)

        parquet_bytes = csv_to_parquet(df)

        report_period = derive_report_period(df)
        paths, manifest = build_manifest(
            report_period,
            vendor=settings.vendor,
            root_dir=settings.dest_container,
            optional_sub_directories=settings.optional_sub_directories,
            report_prefix=settings.report_prefix,
            focus_version=settings.focus_version,
        )

        upload_outputs(
            settings.dest_account_url,
            settings.dest_container,
            parquet_bytes,
            manifest,
            paths,
        )

        logger.info(
            "Daily pipeline run complete: %s/%s",
            settings.dest_container, paths["base_path"],
        )
        return 0
    except Exception:
        # Non-zero exit makes the GitLab CI job show as failed, which is
        # what actually surfaces a problem (pipeline notifications, a red
        # badge) instead of it failing silently.
        logger.exception("Daily pipeline run failed")
        return 1


if __name__ == "__main__":
    sys.exit(run())
