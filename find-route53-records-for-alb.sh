#!/usr/bin/env bash
#
# find_r53_records_for_alb.sh
#
# Searches every Route 53 hosted zone in the account for records
# (alias or CNAME) that point at a given ALB DNS name, and prints a
# clean summary of only the zones/records that actually matched.
#
# Usage:
#   ./find_r53_records_for_alb.sh <alb-dns-name> [aws-profile]
#
# Example:
#   ./find_r53_records_for_alb.sh my-alb-123456.us-east-1.elb.amazonaws.com
#   ./find_r53_records_for_alb.sh my-alb-123456.us-east-1.elb.amazonaws.com myprofile
#
# Requires: aws cli v2, jq

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <alb-dns-name> [aws-profile]"
  echo "Example: $0 my-alb-123456.us-east-1.elb.amazonaws.com"
  exit 1
fi

ALB_DNS="$1"
PROFILE_ARG=()
if [ $# -ge 2 ]; then
  PROFILE_ARG=(--profile "$2")
fi

# Route 53 stores DNS names with a trailing dot
ALB_DNS_DOT="${ALB_DNS%.}."

if ! command -v jq &> /dev/null; then
  echo "This script requires jq. Install it first (e.g. apt install jq / brew install jq)."
  exit 1
fi

echo "Searching all hosted zones for records pointing at: $ALB_DNS_DOT"
echo "----------------------------------------------------------------"

ZONE_IDS=$(aws route53 list-hosted-zones "${PROFILE_ARG[@]}" \
  --query 'HostedZones[].Id' --output text | tr '\t' '\n' | sed 's|/hostedzone/||')

if [ -z "$ZONE_IDS" ]; then
  echo "No hosted zones found in this account (or account/profile has no Route 53 access)."
  exit 0
fi

TOTAL_ZONES=0
MATCH_COUNT=0

for zone_id in $ZONE_IDS; do
  TOTAL_ZONES=$((TOTAL_ZONES + 1))

  zone_name=$(aws route53 get-hosted-zone "${PROFILE_ARG[@]}" \
    --id "$zone_id" --query 'HostedZone.Name' --output text 2>/dev/null || echo "unknown")

  records_json=$(aws route53 list-resource-record-sets "${PROFILE_ARG[@]}" \
    --hosted-zone-id "$zone_id" --output json 2>/dev/null || echo '{"ResourceRecordSets":[]}')

  # Match either:
  #  - Alias record whose AliasTarget.DNSName equals the ALB DNS name
  #  - Non-alias record (e.g. CNAME) whose ResourceRecords value contains the ALB DNS name
  matches=$(echo "$records_json" | jq -r --arg alb "$ALB_DNS_DOT" '
    .ResourceRecordSets[]
    | select(
        (.AliasTarget.DNSName == $alb)
        or ((.ResourceRecords // []) | any(.Value | contains($alb | rtrimstr("."))))
      )
    | "\(.Name)\t\(.Type)\t" + (if .AliasTarget then "ALIAS -> " + .AliasTarget.DNSName else (.ResourceRecords[0].Value // "n/a") end)
  ')

  if [ -n "$matches" ]; then
    MATCH_COUNT=$((MATCH_COUNT + 1))
    echo ""
    echo "Zone: $zone_name (id: $zone_id)"
    printf "  %-40s %-8s %s\n" "RECORD NAME" "TYPE" "TARGET"
    while IFS=$'\t' read -r name type target; do
      printf "  %-40s %-8s %s\n" "$name" "$type" "$target"
    done <<< "$matches"
  fi
done

echo ""
echo "----------------------------------------------------------------"
echo "Zones checked: $TOTAL_ZONES"
echo "Zones with a match: $MATCH_COUNT"

if [ "$MATCH_COUNT" -eq 0 ]; then
  echo ""
  echo "No Route 53 records found pointing at $ALB_DNS across any hosted zone."
  echo "This is a signal (not proof) that the ALB may be unused/orphaned -- also check"
  echo "CloudFront origins, other DNS providers, and hardcoded references in app configs."
fi
