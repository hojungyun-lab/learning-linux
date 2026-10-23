#!/usr/bin/env bash
# L7 네트워크 지연 세부 구간 계측 스크립트 (cURL 정밀 포맷팅)
set -euo pipefail

TARGET_URL="${1:-http://chaos-target:8000/health}"

echo "=========================================================="
echo " 🌐 L7 HTTP 네트워크 지연 세부 구간 계측 (Target: ${TARGET_URL})"
echo "=========================================================="

FORMAT='
  DNS Lookup Time       : %{time_namelookup}s
  TCP Connect Time      : %{time_connect}s
  TLS Handshake Time    : %{time_appconnect}s
  Pre-transfer Time     : %{time_pretransfer}s
  Start Transfer (TTFB) : %{time_starttransfer}s
  --------------------------------------------------
  Total Time            : %{time_total}s
  HTTP Status Code      : %{http_code}
  Remote IP / Port      : %{remote_ip}:%{remote_port}
  Size Downloaded       : %{size_download} bytes
'

curl -w "${FORMAT}" -o /dev/null -s "${TARGET_URL}"
echo "=========================================================="
