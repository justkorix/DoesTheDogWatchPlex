FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dtdd.py plex_warnings.py ./

# Cache and config mount points
VOLUME ["/app/.cache", "/app/config"]

# Default: run once then exit (good for cron/scheduled containers)
# Override CMD or set SCHEDULE for recurring runs
ENV PLEX_URL=""
ENV PLEX_TOKEN=""
ENV DTDD_API_KEY=""
ENV PLEX_LIBRARIES=""
ENV MIN_YES_VOTES="5"
ENV MIN_YES_RATIO="0.7"
ENV SHOW_SAFE_TOPICS="false"
ENV SCHEDULE=""
ENV DRY_RUN="false"

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
