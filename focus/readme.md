# FOCUS Ingest Pipeline (GitLab CI)

Automates the previously-manual process: downloading the Azure Cost
Management Exports, transforming them to FOCUS-compliant Parquet, and
uploading the result (with a manifest.json) to the storage container
Cloudability reads from. Runs as a scheduled GitLab CI pipeline, or on demand.

Supports **multiple subscriptions**: each subscription has its own scheduled
export folder, and the pipeline combines them into one Parquet per month.

## Structure

```
focus_ingest_gitlab/
  focus_transform/
    auth.py              # credential selection: AKS Workload Identity, with
                         # a fallback to DefaultAzureCredential for local runs
    config.py            # settings, loaded from environment variables
    schema.py            # FOCUS column validation (logs warnings, non-fatal)
    transform.py         # load CSV (handles gzip automatically), clean
                         # BillingAccountId, convert to Parquet (snappy)
    manifest.py          # report-period (calendar month) + manifest.json
    storage.py           # blob download/upload + finding the latest exports
    pipeline.py          # unattended entry point - used by GitLab CI
    cli.py               # interactive entry point - single file, local testing
    __init__.py
  tests/
    test_transform.py    # unit tests, no Azure connection required
  .gitlab-ci.yml         # the scheduled pipeline definition
  requirements.txt
  sample_focus_export.csv  # fixture for local dry runs
```

`storage.py` imports `auth.py`, so both files must be in the repo.

`pipeline.py` is what runs in CI. With no file path given, it:

1. Lists the export files under each `SOURCE_PREFIX` folder (one per
   subscription) and groups them by billing-period folder
   (`.../20261101-20261130/<run-guid>/`).
2. For the newest period(s), takes the **newest run from every
   subscription**, including **all part files** of that run (Azure splits
   large exports into `part_0_0001.csv.gz`, `part_1_0001.csv.gz`, ...).
3. Combines everything into one DataFrame, cleans `BillingAccountId`,
   converts to Parquet, and uploads one Parquet + manifest per period.

`cli.py` is for local testing against a single file and is not used by the
CI job. It does not do the multi-subscription combine.

### Safety rules (deliberate failures / skips)

- A subscription folder with no export at all fails the run.
- A period that some subscription doesn't have yet is **skipped with a
  warning** and not uploaded partially. Each upload to Cloudability must be
  the complete month-to-date data, so a partial upload would drop a
  subscription from Cloudability. If no period is complete for every
  subscription, the run fails (`No period has an export for every prefix`).
- Files from different report periods are never mixed in one upload.

## One-time setup

### 1. Identity (AKS Workload Identity)

The job runs on an AKS-based GitLab runner and authenticates with a managed
identity through Workload Identity. No client secret is stored in GitLab.

- Create a user-assigned managed identity with a federated credential for the
  runner's ServiceAccount (your Terraform `workload_identities` setup).
- Grant it **Storage Blob Data Contributor** on the container (or storage
  account). Source and destination are both the `reports` container, so one
  role covers reading the exports and writing the output. If they are
  separate accounts, grant `Storage Blob Data Reader` on the source and
  `Storage Blob Data Contributor` on the destination.
- The runner pod must have the label `azure.workload.identity/use: "true"`
  and use the configured ServiceAccount. The webhook then injects
  `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_FEDERATED_TOKEN_FILE`,
  which `auth.py` uses (`WorkloadIdentityCredential`). If the token file is
  missing, the job fails with a message pointing at the label/ServiceAccount.
- No `az` CLI or `az login` is needed in the job; the Python SDK handles it.

Local runs: `auth.py` falls back to `DefaultAzureCredential`, so `az login`
works on your machine.

### 2. GitLab CI/CD variables

Project **Settings > CI/CD > Variables**. Protected variables are only
available on protected branches/tags, so run the job from one of those (or
leave non-secret values unprotected).

| Variable | Value |
|---|---|
| `SOURCE_ACCOUNT_URL` | `https://<source-account>.blob.core.windows.net` (same as `FOCUS_DEST_ACCOUNT_URL` if they share one storage account) |
| `SOURCE_CONTAINER` | Container the Cost Management Exports write to (e.g. `reports`) |
| `SOURCE_PREFIX` | One folder **per subscription export**, comma-separated, e.g. `daily/PRD-TestProdExport/,daily/shared-sub-focus-cost/`. Adding a subscription later is just an edit here, no code change |
| `FOCUS_DEST_ACCOUNT_URL` | `https://<destination-account>.blob.core.windows.net` |
| `FOCUS_DEST_CONTAINER` | Your Cloudability "Root Directory" container name |
| `FOCUS_VENDOR` | Must match Cloudability's credential config exactly (e.g. `Microsoft Azure`) |
| `FOCUS_REPORT_PREFIX` | Must match Cloudability's "Manifest Prefix" field exactly (e.g. `reports`) |

Optional:

| Variable | Default | Purpose |
|---|---|---|
| `FOCUS_MAX_PERIODS` | `1` | How many of the most recent billing periods to process each run. `1` = current month only. Set `2` to also refresh last month (e.g. once, to upload its final numbers after month end) |
| `FOCUS_SUB_DIRECTORIES` | empty | Cloudability "Sub Directories", if used |
| `FOCUS_SPEC_VERSION` | `1.0` | FOCUS version written to the manifest |

### 3. Create the daily schedule

Project **Build > Pipeline schedules > New schedule**. Use cron syntax
(e.g. `0 6 * * *` for 6am daily), set your timezone, and target the branch
this code lives on. Schedule it well after the exports normally finish: part
files land at slightly different times, and running mid-delivery could pick
up an incomplete set.

## Running it

**On its schedule** - no action needed once set up above.

**Manually, any time**, two ways:

1. **GitLab UI:** Project > Build > Pipelines > **Run pipeline**, pick the
   branch, run. (Works because the job's `rules` in `.gitlab-ci.yml` allow
   `$CI_PIPELINE_SOURCE == "web"`, which is what a UI-triggered run reports.)
2. **API / trigger token** (Project > Settings > CI/CD > Pipeline trigger
   tokens > create one):
   ```bash
   curl -X POST \
     -F token=<your-trigger-token> \
     -F ref=main \
     https://gitlab.example.com/api/v4/projects/<project-id>/trigger/pipeline
   ```

Both manual options run the exact same job the schedule runs. Triggering a
run close to the scheduled time just means two runs land in two different
epoch-time folders in the destination container - not an overwrite, but
worth being aware of if you're testing repeatedly.

## Reading the job log

A healthy run shows, per period:

- `Period 20261101-20261130, prefix '...' -> <run folder>, N part(s)` for
  every subscription
- `Combined N export file(s): rows per file=[...]`
- `Rows per SubAccountId: {...}` listing every subscription
- `Period ... uploaded: <container>/<path>`

Things to act on:

- `Skipping period ...: no export yet under [...]` - that subscription has no
  export for the period yet (or its folder/prefix doesn't match).
- `N rows still have an un-cleaned BillingAccountId` - a subscription's
  `BillingAccountId` format isn't covered by the cleanup in `transform.py`.
- `Exports span different report periods` - should not occur with the
  per-period logic; indicates unexpected data in an export file.

## Local testing (before relying on this in CI)

```bash
python3 -m pip install -r requirements.txt
pytest tests/

# Dry run against the sample file - writes Parquet + manifest to disk, no upload
python -m focus_transform.cli --input sample_focus_export.csv --output-dir ./out

# Dry run against a real export you've downloaded yourself (single file)
python -m focus_transform.cli --input your_export.csv.gz --output-dir ./out
```

To test the actual unattended pipeline locally (fetching from the container,
same as CI would), `az login` first, set the variables above, and run:

```bash
export SOURCE_ACCOUNT_URL=... SOURCE_CONTAINER=... SOURCE_PREFIX=...
export FOCUS_DEST_ACCOUNT_URL=... FOCUS_DEST_CONTAINER=...
python -m focus_transform.pipeline
```

Note this uploads to the real destination container.

## Known open items

- **Manifest field confirmation:** the `compression` field in IBM's sample
  manifest shows `"GZIP"` next to a `.snappy.parquet` filename, which is
  internally inconsistent. This code reports the actual Parquet codec used
  (`SNAPPY`) rather than copying the sample literally - worth confirming
  with IBM/Cloudability support which one their ingestion actually expects.
- **One combined upload:** all subscriptions go into a single Parquet per
  month. Cloudability reads the latest epoch folder for a period, so each
  upload must contain every subscription. Worth confirming this model with
  IBM.
- **BillingAccountId format:** the cleanup only strips the
  `/providers/Microsoft.Billing/billingAccounts/` prefix. Check the log
  warning if a new subscription's export uses a different format.
- **Memory:** all files for a period are held in memory at once. Many
  subscriptions or very large exports may need a higher runner pod memory
  limit.
- **Historical/backfill months:** the pipeline only processes the newest
  period(s) at run time. Past months need a deliberate backfill (run once
  with `FOCUS_MAX_PERIODS` set high enough, or process the historical export
  through `cli.py` and upload to its own correctly-dated folder).
