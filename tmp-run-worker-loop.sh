#!/usr/bin/env bash
set -euo pipefail
source /etc/ocr-platform.env
while true; do
  curl -s -X POST http://127.0.0.1:3000/api/jobs     -H "content-type: application/json"     -H "x-worker-key: ${OCR_WORKER_API_KEY}"     --data-binary '{"action":"run_worker","limit":5,"concurrency":1}' >/dev/null || true
  sleep 30
done
