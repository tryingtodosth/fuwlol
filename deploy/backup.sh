#!/usr/bin/env bash
# Nightly: the database, the evidence volume, and whatever media is still local.
#
# OVH's own snapshot and Standard automated backup cover the whole disk, and they are the
# fast way back from "I broke the server". They are not the way back from "the OVH account
# is suspended" or "the region is gone", because they live in the same place as the thing
# they protect. So this is the off-site half: encrypted by restic, pushed to R2, which
# charges nothing for the egress if it is ever needed.
#
# What is NOT here, deliberately: the attachment objects in R2. They are already off-box
# and already replicated by Cloudflare; copying them into a restic repo in the same bucket
# would double the storage to protect against nothing. What IS here is the `evidence`
# volume — the frozen escalation packages — because those exist in exactly one place and
# are the records behind a report to a national authority.
#
#   0 3 * * *  /srv/fuwlol/deploy/backup.sh >> /var/log/fuwlol-backup.log 2>&1
set -euo pipefail

cd /srv/fuwlol
set -a; . ./.env; set +a
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

STAMP=$(date +%F_%H%M)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# -Fc: the custom format, which restores selectively and compresses. Streamed straight out
# of the container so nothing is written to the host unencrypted for longer than this run.
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U fuwlol -Fc fuwlol > "$WORK/fuwlol-$STAMP.dump"

# The evidence volume, read out of a throwaway container because it belongs to `api`.
docker run --rm -v fuwlol_evidence:/evidence:ro -v "$WORK:/out" alpine \
  tar czf "/out/evidence-$STAMP.tar.gz" -C /evidence .

# Local media only matters while R2 is off; with R2 configured this is a few kilobytes.
docker run --rm -v fuwlol_media:/media:ro -v "$WORK:/out" alpine \
  tar czf "/out/media-$STAMP.tar.gz" -C /media .

restic backup --tag nightly "$WORK"
restic forget --tag nightly --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune

# A backup nobody has ever restored is a hypothesis. This checks a random 5% of the data
# each night, so the hypothesis is tested continuously instead of on the worst day.
restic check --read-data-subset=5%
echo "backup ok $STAMP"
