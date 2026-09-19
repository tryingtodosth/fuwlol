#!/usr/bin/env bash
# Only Cloudflare may reach 80/443. Everything else: SSH, and nothing.
#
# THE TRAP THIS SCRIPT EXISTS FOR: Docker does not go through ufw. A published port
# (`ports: 80:80`) is a DNAT rule that jumps straight into Docker's own chains, so
# `ufw deny 80` looks correct in `ufw status`, blocks nothing, and you find out when
# somebody hits the origin IP directly. The supported place to filter container traffic is
# the DOCKER-USER chain, which Docker consults before its own rules and never rewrites.
#
# This matters more than usual here, because docker-compose.prod.yml sets
# FUWLOL_CLOUDFLARE=1 — Django trusts CF-Connecting-IP for every per-IP throttle and every
# stored ip_hash. That header is trustworthy ONLY while nobody can talk to the origin
# except Cloudflare. This script is what makes that setting true; without it the setting
# is a hole, which is why config/middleware.py says so in as many words.
#
#   sudo ./firewall.sh          # apply now
#   systemd installs it at boot and refreshes the ranges weekly (see deploy/OVH.md)
set -euo pipefail

CHAIN=FUWLOL-CF
V4_URL=https://www.cloudflare.com/ips-v4
V6_URL=https://www.cloudflare.com/ips-v6

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

apply() {
  local ipt=$1 url=$2 ranges
  # Fetched fresh, not pinned: Cloudflare adds ranges, and a stale list fails CLOSED —
  # visitors from a new range would be dropped. Refuse to apply an empty list rather than
  # write a firewall that blocks everybody because a download failed.
  ranges=$(curl -fsS --max-time 20 "$url") || { echo "could not fetch $url" >&2; return 1; }
  [ -n "$ranges" ] || { echo "$url returned nothing" >&2; return 1; }

  $ipt -N "$CHAIN" 2>/dev/null || true
  $ipt -F "$CHAIN"
  while read -r net; do
    [ -n "$net" ] || continue
    $ipt -A "$CHAIN" -s "$net" -j RETURN        # a Cloudflare address: carry on
  done <<< "$ranges"
  $ipt -A "$CHAIN" -j DROP                       # anybody else, on 80/443: gone

  # Hook it in once, idempotently, for the two ports only. Container-to-container traffic
  # and the SSH port are untouched.
  for port in 80 443; do
    $ipt -C DOCKER-USER -p tcp --dport "$port" -j "$CHAIN" 2>/dev/null || \
      $ipt -I DOCKER-USER -p tcp --dport "$port" -j "$CHAIN"
    $ipt -C DOCKER-USER -p udp --dport "$port" -j "$CHAIN" 2>/dev/null || \
      $ipt -I DOCKER-USER -p udp --dport "$port" -j "$CHAIN"   # HTTP/3
  done
  echo "$ipt: $(wc -l <<< "$ranges") Cloudflare ranges allowed on 80/443"
}

apply iptables  "$V4_URL"
apply ip6tables "$V6_URL"

# The host's own ports (SSH) are ufw's job; Docker's are the chain above. Both, not either.
ufw --force default deny incoming >/dev/null
ufw --force default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw --force enable >/dev/null
echo "ufw: default deny incoming, 22/tcp open (key-only auth)"
