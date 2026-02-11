#!/bin/sh
set -e

# Generate config.py from environment variables
cat > /app/config.py <<EOF
PLEX_URL = "${PLEX_URL}"
PLEX_TOKEN = "${PLEX_TOKEN}"
DTDD_API_KEY = "${DTDD_API_KEY}"
SEPARATOR = "\n\n———— Content Warnings (via DoesTheDogDie.com) ————"
MIN_YES_VOTES = ${MIN_YES_VOTES:-5}
MIN_YES_RATIO = ${MIN_YES_RATIO:-0.7}
SHOW_SAFE_TOPICS = ${SHOW_SAFE_TOPICS:-False}
CACHE_TTL = 604800
API_DELAY = 1.0
DRY_RUN = ${DRY_RUN:-False}
EOF

# Handle PLEX_LIBRARIES (comma-separated string to Python list)
if [ -n "$PLEX_LIBRARIES" ]; then
    # Convert "Movies,TV Shows" to ["Movies", "TV Shows"]
    PYLIST=$(echo "$PLEX_LIBRARIES" | python3 -c "
import sys
libs = [l.strip() for l in sys.stdin.read().strip().split(',') if l.strip()]
print(repr(libs))
")
    echo "PLEX_LIBRARIES = $PYLIST" >> /app/config.py
else
    echo "PLEX_LIBRARIES = None" >> /app/config.py
fi

# Validate required vars
if [ -z "$PLEX_URL" ] || [ -z "$PLEX_TOKEN" ] || [ -z "$DTDD_API_KEY" ]; then
    echo "ERROR: PLEX_URL, PLEX_TOKEN, and DTDD_API_KEY are required."
    echo ""
    echo "Example:"
    echo "  docker run -e PLEX_URL=http://plex:32400 -e PLEX_TOKEN=xxx -e DTDD_API_KEY=xxx ghcr.io/you/doesthedogwatchplex"
    exit 1
fi

# If SCHEDULE is set, run on a loop. Otherwise run once and exit.
if [ -n "$SCHEDULE" ]; then
    echo "Running on schedule: every ${SCHEDULE} seconds"
    while true; do
        echo ""
        echo "=== $(date) ==="
        python3 /app/plex_warnings.py "$@"
        echo "Sleeping ${SCHEDULE}s..."
        sleep "$SCHEDULE"
    done
else
    python3 /app/plex_warnings.py "$@"
fi
