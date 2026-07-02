#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Log to stderr so MCP stdio protocol isn't polluted
log() { echo "$@" >&2; }

# Try to start SearXNG if not already running
if curl -s http://localhost:8088/health > /dev/null 2>&1; then
  log "SearXNG is already running."
else
  log "Starting SearXNG container..."
  if ! docker compose up -d 2>&1; then
    log "Warning: Failed to start SearXNG via Docker."
    log "Start manually with: docker compose up -d"
  fi

  # Wait for SearXNG to be ready
  log "Waiting for SearXNG to be ready on port 8088..."
  for i in $(seq 1 30); do
    if curl -s http://localhost:8088/health > /dev/null 2>&1; then
      log "SearXNG is ready!"
      break
    fi
    if [ "$i" -eq 30 ]; then
      log "Warning: SearXNG did not become ready in 30 seconds."
      log "Check with: docker compose logs"
    fi
    sleep 1
  done
fi

log "Starting MCP server..."
exec uv run web-search-mcp
