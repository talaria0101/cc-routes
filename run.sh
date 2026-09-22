#!/usr/bin/env bash
# cc-routes one-command refresh: static spec + runtime drive + analysis.
# Stdlib only (python3 + gcc for the netlog tap + bun to run the CLI).
set -u
cd "$(dirname "$0")"

MODE="full"
PASS=()
for a in "$@"; do
  case "$a" in
    --report-only) MODE="report";;
    --offline) MODE="offline";;
    *) PASS+=("$a");;
  esac
done

case "$MODE" in
  report)
    # offline: re-render all human reports from committed data, no network
    python3 cc_routes.py --report-only "${PASS[@]}" || exit $?
    python3 mitm/analyze.py --report-only "${PASS[@]}" || exit $?
    ;;
  offline)
    python3 cc_routes.py --no-fetch-sources --spec-only "${PASS[@]}" || exit $?
    ;;
  full)
    python3 cc_routes.py "${PASS[@]}" || exit $?
    python3 mitm/drive.py --work ./mitm/work --captures ./mitm/captures \
      "${PASS[@]}" || exit $?
    python3 mitm/analyze.py --captures ./mitm/captures \
      --spec ./spec/api-spec.json "${PASS[@]}"
    rc=$?
    if [ $rc -eq 1 ]; then
      echo "analyze verdict: unknown hosts (see NEW_ENDPOINTS.md)" >&2
    fi
    exit $rc
    ;;
esac
