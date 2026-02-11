# DoesTheDogWatchPlex

Add content warnings from [DoesTheDogDie.com](https://www.doesthedogdie.com) to your Plex movie summaries — so anyone browsing your library can see trigger warnings without leaving the Plex interface.

Rebuilt from [valknight/DoesTheDogWatchPlex](https://github.com/valknight/DoesTheDogWatchPlex) (2018) for modern Plex and the current DTDD API.

## What It Does

For each movie in your Plex library, the script:

1. Matches it to DoesTheDogDie.com (by IMDB ID first, then title/year)
2. Fetches community-voted content warnings (animal death, sexual assault, etc.)
3. Appends a formatted warning block to the movie's summary in Plex

The result looks like this in Plex:

```
Original movie summary here...

———— Content Warnings (via DoesTheDogDie.com) ————
⚠️  a dog dies · an animal is sad · someone is buried alive
✅  no cats die · nobody is stalked
```

Warnings are filtered by vote count and confidence ratio, so you only see things the community is reasonably sure about.

## Setup

### Docker (recommended)

```bash
git clone https://github.com/justkorix/DoesTheDogWatchPlex.git
cd DoesTheDogWatchPlex
```

Edit `docker-compose.yml` with your Plex URL, token, and DTDD API key, then:

```bash
# Preview first
docker compose run --rm doesthedogwatchplex --dry-run

# Run once
docker compose run --rm doesthedogwatchplex

# Run as a background service (re-scans every 24h by default)
docker compose up -d
```

Or run directly with `docker run`:

```bash
docker run --rm \
  -e PLEX_URL=http://YOUR_PLEX_IP:32400 \
  -e PLEX_TOKEN=your-plex-token \
  -e DTDD_API_KEY=your-dtdd-api-key \
  -v dtdd-cache:/app/.cache \
  ghcr.io/YOURUSERNAME/doesthedogwatchplex --dry-run
```

Set `SCHEDULE=86400` to re-scan every 24 hours, or omit it to run once and exit.

### Manual (no Docker)

**Prerequisites:** Python 3.7+, a Plex server, a DoesTheDogDie.com account.

```bash
# Clone or copy the files to your server
cd ~/DoesTheDogWatchPlex

# Create a virtual environment (no sudo needed)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp config.py.example config.py
# Edit config.py with your Plex URL, token, and DTDD API key
```

### Getting Your Credentials

**Plex Token:** Open Plex in a browser, play any media, and inspect network requests for the `X-Plex-Token` parameter. Or see [Plex's guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

**DTDD API Key:** Create an account at [doesthedogdie.com](https://www.doesthedogdie.com/signup), then visit your [profile page](https://www.doesthedogdie.com/profile) to find your API key.

## Usage

```bash
# Activate venv first
source venv/bin/activate

# Preview what would change (safe, doesn't modify Plex)
python plex_warnings.py --dry-run

# Run it for real
python plex_warnings.py

# Process a single movie
python plex_warnings.py --movie "Midsommar"

# Remove all content warnings from your library
python plex_warnings.py --clear

# Clear the local API cache (forces fresh DTDD lookups)
python plex_warnings.py --clear-cache
```

### Running on a Schedule (cron)

To automatically process new additions:

```bash
crontab -e
```

Add a line like this to run nightly at 3am:

```
0 3 * * * cd ~/DoesTheDogWatchPlex && venv/bin/python plex_warnings.py >> dtdd.log 2>&1
```

## Configuration

All settings are in `config.py`. Key options:

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `PLEX_LIBRARIES` | `PLEX_LIBRARIES` | `["Movies"]` | Which libraries to process. `None`/empty = all movie libraries |
| `MIN_YES_VOTES` | `MIN_YES_VOTES` | `5` | Minimum "yes" votes to include a warning |
| `MIN_YES_RATIO` | `MIN_YES_RATIO` | `0.7` | Minimum ratio of yes/(yes+no) to flag a warning |
| `SHOW_SAFE_TOPICS` | `SHOW_SAFE_TOPICS` | `False` | Include the ✅ "safe" list (e.g., "no dogs die") |
| `API_DELAY` | - | `1.0` | Seconds between DTDD API calls |
| `CACHE_TTL` | - | `604800` | Cache duration in seconds (default: 7 days) |
| `DRY_RUN` | `DRY_RUN` | `False` | Set to `True` to preview without writing |
| - | `SCHEDULE` | - | Docker only: seconds between re-runs (e.g., `86400` for daily) |

## How It Works

- **Matching:** Tries IMDB ID first (via Plex's GUID metadata), then falls back to title+year search against the DTDD API.
- **Caching:** API responses are cached locally in `.cache/` as JSON files to avoid hammering DTDD on re-runs.
- **Idempotent:** Safe to re-run. Existing warnings are stripped and replaced with fresh data each time.
- **Reversible:** `--clear` removes all DTDD-added content from summaries, restoring originals.

## License

MIT
