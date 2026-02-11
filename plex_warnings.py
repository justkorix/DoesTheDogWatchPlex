#!/usr/bin/env python3
"""
DoesTheDogWatchPlex — Content warnings from DoesTheDogDie.com in your Plex library.

Usage:
    python plex_warnings.py              # Process all configured libraries
    python plex_warnings.py --dry-run    # Preview changes without writing
    python plex_warnings.py --clear      # Remove all content warnings from Plex
    python plex_warnings.py --clear-cache  # Clear the local DTDD API cache
    python plex_warnings.py --movie "Midsommar"  # Process a single movie by title
"""
from __future__ import annotations

import argparse
import sys
import time

from plexapi.server import PlexServer

from dtdd import DTDDClient

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    print("Copy config.py.example to config.py and fill in your details.")
    sys.exit(1)


def get_separator() -> str:
    return getattr(config, "SEPARATOR", "\n\n———— Content Warnings (via DoesTheDogDie.com) ————")


def strip_warnings(summary: str) -> str:
    """Remove existing DTDD content warnings from a summary."""
    sep = get_separator()
    if sep in summary:
        return summary.split(sep)[0].rstrip()
    # Also handle the old-style separator from the original project
    if "\ndoesthedogdie:" in summary.lower():
        for i, line in enumerate(summary.split("\n")):
            if line.strip().lower().startswith("doesthedogdie:"):
                return "\n".join(summary.split("\n")[:i]).rstrip()
    return summary


def format_warnings(media_data: dict) -> str | None:
    """Extract and format trigger warnings from DTDD media response.

    Returns a formatted string of warnings, or None if no relevant warnings found.
    """
    stats = media_data.get("topicItemStats", [])
    if not stats:
        return None

    min_yes = getattr(config, "MIN_YES_VOTES", 3)
    min_ratio = getattr(config, "MIN_YES_RATIO", 0.6)

    show_nos = getattr(config, "SHOW_SAFE_TOPICS", False)
    warnings_yes = []
    warnings_no = []

    for stat in stats:
        yes_count = stat.get("yesSum", 0)
        no_count = stat.get("noSum", 0)
        total = yes_count + no_count
        topic = stat.get("topic", {})
        topic_name = topic.get("name", "")
        topic_not_name = topic.get("notName", "")

        if total == 0 or not topic_name:
            continue

        ratio = yes_count / total

        if ratio >= min_ratio and yes_count >= min_yes:
            warnings_yes.append((topic_name, yes_count, no_count))
        elif show_nos and (1 - ratio) >= min_ratio and no_count >= min_yes:
            warnings_no.append((topic_not_name, yes_count, no_count))

    if not warnings_yes and not warnings_no:
        return None

    lines = []
    if warnings_yes:
        lines.append("⚠️  " + " · ".join(w[0] for w in warnings_yes))
    if warnings_no:
        lines.append("✅  " + " · ".join(w[0] for w in warnings_no))

    return "\n".join(lines)


def match_movie(dtdd: DTDDClient, movie) -> dict | None:
    """Try to match a Plex movie to a DTDD entry.

    Strategy:
    1. Search by IMDB ID if available (most reliable)
    2. Fall back to title + year search
    3. Try title-only search as last resort

    Returns the DTDD media data dict, or None if no match.
    """
    title = movie.title
    year = movie.year

    # Try IMDB ID first (available via guids on modern Plex)
    imdb_id = None
    try:
        for guid in movie.guids:
            if guid.id.startswith("imdb://"):
                imdb_id = guid.id.replace("imdb://", "")
                break
    except Exception:
        pass

    if imdb_id:
        results = dtdd.search_by_imdb(imdb_id)
        if results:
            return dtdd.get_media(results[0]["id"])

    # Fall back to title search
    results = dtdd.search(title)
    if not results:
        return None

    # Try to match by year if we have it
    if year:
        for item in results:
            item_year = item.get("releaseYear", "")
            if str(year) == str(item_year):
                return dtdd.get_media(item["id"])

    # If no year match, take the first Movie result
    for item in results:
        item_type = item.get("itemType", {}).get("name", "")
        if item_type == "Movie":
            return dtdd.get_media(item["id"])

    # Last resort: first result
    return dtdd.get_media(results[0]["id"])


def process_movie(dtdd: DTDDClient, movie, dry_run: bool = False) -> bool:
    """Process a single movie. Returns True if the summary was updated."""
    title = f"{movie.title} ({movie.year})" if movie.year else movie.title

    # Skip if already has warnings and we're not in a re-run
    original_summary = movie.summary or ""
    clean_summary = strip_warnings(original_summary)

    # Try to match and get warnings
    try:
        media_data = match_movie(dtdd, movie)
    except Exception as e:
        print(f"  ✗ {title} — API error: {e}")
        return False

    if not media_data:
        print(f"  – {title} — not found on DTDD")
        return False

    warning_text = format_warnings(media_data)
    if not warning_text:
        print(f"  – {title} — no significant warnings")
        return False

    new_summary = clean_summary + get_separator() + "\n" + warning_text

    if dry_run:
        print(f"  ✓ {title} — would add warnings:")
        for line in warning_text.split("\n"):
            print(f"      {line}")
        return True

    try:
        movie.editSummary(new_summary)
        print(f"  ✓ {title} — warnings added")
        return True
    except Exception as e:
        print(f"  ✗ {title} — failed to update: {e}")
        return False


def clear_warnings(plex: PlexServer, library_names: list[str] | None):
    """Remove all DTDD content warnings from movie summaries."""
    libraries = get_libraries(plex, library_names)
    total_cleared = 0

    for lib in libraries:
        print(f"\nClearing warnings from: {lib.title}")
        for movie in lib.all():
            original = movie.summary or ""
            cleaned = strip_warnings(original)
            if cleaned != original:
                movie.editSummary(cleaned)
                print(f"  ✓ {movie.title} — warnings removed")
                total_cleared += 1

    print(f"\nDone. Cleared warnings from {total_cleared} movie(s).")


def get_libraries(plex: PlexServer, library_names: list[str] | None):
    """Get movie libraries to process."""
    if library_names:
        libraries = []
        for name in library_names:
            try:
                lib = plex.library.section(name)
                if lib.type == "movie":
                    libraries.append(lib)
                else:
                    print(f"Warning: '{name}' is not a movie library (type: {lib.type}), skipping.")
            except Exception:
                print(f"Warning: Library '{name}' not found, skipping.")
        return libraries
    else:
        return [s for s in plex.library.sections() if s.type == "movie"]


def main():
    parser = argparse.ArgumentParser(
        description="Add DoesTheDogDie.com content warnings to your Plex movie summaries."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without modifying Plex")
    parser.add_argument("--clear", action="store_true",
                        help="Remove all content warnings from Plex summaries")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Clear the local DTDD API response cache")
    parser.add_argument("--movie", type=str,
                        help="Process a single movie by title (exact match)")
    args = parser.parse_args()

    dry_run = args.dry_run or getattr(config, "DRY_RUN", False)

    # Handle cache clear
    if args.clear_cache:
        client = DTDDClient(config.DTDD_API_KEY)
        client.clear_cache()
        if not args.clear and not args.movie:
            return

    # Connect to Plex
    print(f"Connecting to Plex at {config.PLEX_URL}...")
    try:
        plex = PlexServer(config.PLEX_URL, config.PLEX_TOKEN)
        print(f"Connected to: {plex.friendlyName}")
    except Exception as e:
        print(f"ERROR: Could not connect to Plex: {e}")
        sys.exit(1)

    library_names = getattr(config, "PLEX_LIBRARIES", None)

    # Handle clear mode
    if args.clear:
        clear_warnings(plex, library_names)
        return

    # Initialize DTDD client
    dtdd = DTDDClient(
        api_key=config.DTDD_API_KEY,
        cache_ttl=getattr(config, "CACHE_TTL", 604800),
        api_delay=getattr(config, "API_DELAY", 1.0),
    )

    if dry_run:
        print("DRY RUN — no changes will be made to Plex\n")

    # Process single movie or all libraries
    if args.movie:
        libraries = get_libraries(plex, library_names)
        found = False
        for lib in libraries:
            results = lib.search(title=args.movie)
            for movie in results:
                found = True
                process_movie(dtdd, movie, dry_run=dry_run)
        if not found:
            print(f"Movie '{args.movie}' not found in Plex.")
        return

    # Process all movies in configured libraries
    libraries = get_libraries(plex, library_names)
    if not libraries:
        print("No movie libraries found to process.")
        sys.exit(1)

    total_processed = 0
    total_updated = 0
    start_time = time.time()

    for lib in libraries:
        movies = lib.all()
        print(f"\nProcessing: {lib.title} ({len(movies)} movies)")
        print("-" * 50)

        for movie in movies:
            total_processed += 1
            if process_movie(dtdd, movie, dry_run=dry_run):
                total_updated += 1

    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}")
    print(f"Done in {elapsed:.1f}s")
    print(f"Processed: {total_processed} movies")
    print(f"Updated:   {total_updated} movies")
    if dry_run:
        print("(DRY RUN — no actual changes made)")


if __name__ == "__main__":
    main()
