#!/usr/bin/env python3
"""
DoesTheDogWatchPlex — Content warnings from DoesTheDogDie.com in your Plex library.

Usage:
    python plex_warnings.py              # Process all configured libraries
    python plex_warnings.py --dry-run    # Preview changes without writing
    python plex_warnings.py --clear      # Remove all content warnings from Plex
    python plex_warnings.py --clear-cache  # Clear the local DTDD API cache
    python plex_warnings.py --movie "Midsommar"  # Process a single movie by title
    python plex_warnings.py --list-topics  # Show all available topic names for filtering
"""
from __future__ import annotations

import argparse
import sys
import time

from plexapi.server import PlexServer

# Maps PLEX_LIBRARY_TYPES strings to Plex internal type names
_LIBRARY_TYPE_MAP = {
    "movies": "movie",
    "tv_shows": "show",
}

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
    include_topics = getattr(config, "INCLUDE_TOPICS", None)
    exclude_topics = getattr(config, "EXCLUDE_TOPICS", None)

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

        # Apply topic filtering
        if include_topics is not None:
            if topic_name.lower() not in [t.lower() for t in include_topics]:
                continue
        elif exclude_topics is not None:
            if topic_name.lower() in [t.lower() for t in exclude_topics]:
                continue

        ratio = yes_count / total

        if ratio >= min_ratio and yes_count >= min_yes:
            warnings_yes.append((topic_name, yes_count, no_count))
        elif show_nos and (1 - ratio) >= min_ratio and no_count >= min_yes:
            warnings_no.append((topic_not_name, yes_count, no_count))

    if not warnings_yes and not warnings_no:
        return None

    # Translate topic names if LANGUAGE is configured
    target_lang = getattr(config, "LANGUAGE", None)
    if target_lang:
        from translate import translate_topics
        all_names = [w[0] for w in warnings_yes] + [w[0] for w in warnings_no]
        translations = translate_topics(all_names, target_lang)
    else:
        translations = None

    lines = []
    if warnings_yes:
        names = [translations[w[0]] if translations else w[0] for w in warnings_yes]
        lines.append("⚠️  " + " · ".join(names))
    if warnings_no:
        names = [translations[w[0]] if translations else w[0] for w in warnings_no]
        lines.append("✅  " + " · ".join(names))

    return "\n".join(lines)


def _extract_external_ids(item) -> dict[str, str]:
    """Extract known external IDs from a Plex item's guids.

    Returns a dict with any of: 'imdb', 'tvdb'
    """
    ids = {}
    try:
        for guid in item.guids:
            if guid.id.startswith("imdb://"):
                ids["imdb"] = guid.id.replace("imdb://", "")
            elif guid.id.startswith("tvdb://"):
                ids["tvdb"] = guid.id.replace("tvdb://", "")
    except Exception:
        pass
    return ids


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
    ext_ids = _extract_external_ids(movie)

    # Try IMDB ID first
    if "imdb" in ext_ids:
        results = dtdd.search_by_imdb(ext_ids["imdb"])
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


def match_show(dtdd: DTDDClient, show) -> dict | None:
    """Match a Plex show to DTDD and return its full media data.

    Strategy:
    1. Search by IMDB ID if available
    2. Fall back to title search, matching on itemType 'TV Show' and release year
    3. First 'TV Show' result as last resort

    Returns the full DTDD media data dict (with all episode stats), or None.
    """
    ext_ids = _extract_external_ids(show)

    if "imdb" in ext_ids:
        results = dtdd.search_by_imdb(ext_ids["imdb"])
        if results:
            return dtdd.get_media(results[0]["id"])

    results = dtdd.search(show.title)
    if not results:
        return None

    tv_results = [r for r in results if r.get("itemType", {}).get("name") == "TV Show"]

    # Try to match by year within TV results
    if show.year:
        for item in tv_results:
            if str(show.year) == str(item.get("releaseYear", "")):
                return dtdd.get_media(item["id"])

    # First TV Show result
    if tv_results:
        return dtdd.get_media(tv_results[0]["id"])

    return None


def filter_episode_stats(all_stats: list, season: int, episode: int) -> list:
    """Filter show-level topicItemStats down to a specific season/episode."""
    return [
        stat for stat in all_stats
        if stat.get("ratingIndex1") == season and stat.get("ratingIndex2") == episode
    ]


def process_episode(episode, show_media_data: dict, dry_run: bool = False) -> bool:
    """Process a single episode using pre-fetched show media data.

    Filters the show's topicItemStats to this episode's season/episode numbers,
    then formats and writes warnings to the episode summary.
    Returns True if the summary was updated.
    """
    season_num = episode.parentIndex
    episode_num = episode.index
    label = f"S{season_num:02d}E{episode_num:02d}"
    if episode.title:
        label += f" - {episode.title}"

    all_stats = show_media_data.get("topicItemStats", [])
    episode_stats = filter_episode_stats(all_stats, season_num, episode_num)

    if not episode_stats:
        print(f"    – {label} — no episode data on DTDD")
        return False

    warning_text = format_warnings({"topicItemStats": episode_stats})
    if not warning_text:
        print(f"    – {label} — no significant warnings")
        return False

    original_summary = episode.summary or ""
    clean_summary = strip_warnings(original_summary)
    new_summary = clean_summary + get_separator() + "\n" + warning_text

    if dry_run:
        print(f"    ✓ {label} — would add warnings:")
        for line in warning_text.split("\n"):
            print(f"        {line}")
        return True

    try:
        episode.editSummary(new_summary)
        print(f"    ✓ {label} — warnings added")
        return True
    except Exception as e:
        print(f"    ✗ {label} — failed to update: {e}")
        return False


def process_show(dtdd: DTDDClient, show, dry_run: bool = False) -> tuple[int, int]:
    """Process all episodes of a show. Returns (processed, updated) episode counts.

    Fetches show data once from DTDD, then filters in memory per episode.
    """
    print(f"  {show.title}")

    try:
        show_media_data = match_show(dtdd, show)
    except Exception as e:
        print(f"    ✗ API error: {e}")
        return 0, 0

    if not show_media_data:
        print(f"    – not found on DTDD")
        return 0, 0

    matched_name = show_media_data.get("item", {}).get("name", "unknown")
    matched_id = show_media_data.get("item", {}).get("id", "?")
    print(f"    → matched: \"{matched_name}\" (DTDD id: {matched_id})")

    processed = 0
    updated = 0
    for season in show.seasons():
        for episode in season.episodes():
            processed += 1
            if process_episode(episode, show_media_data, dry_run=dry_run):
                updated += 1
    return processed, updated


def clear_warnings(plex: PlexServer, library_names: list[str] | None, library_types: list[str] | None = None):
    """Remove all DTDD content warnings from library summaries."""
    libraries = get_libraries(plex, library_names, library_types)
    total_cleared = 0

    for lib in libraries:
        print(f"\nClearing warnings from: {lib.title}")
        if lib.type == "show":
            for show in lib.all():
                for season in show.seasons():
                    for episode in season.episodes():
                        original = episode.summary or ""
                        cleaned = strip_warnings(original)
                        if cleaned != original:
                            episode.editSummary(cleaned)
                            label = f"S{episode.parentIndex:02d}E{episode.index:02d}"
                            print(f"  ✓ {show.title} {label} — warnings removed")
                            total_cleared += 1
        else:
            for movie in lib.all():
                original = movie.summary or ""
                cleaned = strip_warnings(original)
                if cleaned != original:
                    movie.editSummary(cleaned)
                    print(f"  ✓ {movie.title} — warnings removed")
                    total_cleared += 1

    print(f"\nDone. Cleared warnings from {total_cleared} item(s).")


def get_libraries(plex: PlexServer, library_names: list[str] | None, library_types: list[str] | None = None):
    """Get libraries to process, filtered by type and optional name list."""
    if library_types is None:
        library_types = ["movies"]
    type_values = {_LIBRARY_TYPE_MAP[lt] for lt in library_types if lt in _LIBRARY_TYPE_MAP}

    if library_names:
        libraries = []
        for name in library_names:
            try:
                lib = plex.library.section(name)
                if lib.type in type_values:
                    libraries.append(lib)
                else:
                    print(f"Warning: '{name}' has type '{lib.type}', not in PLEX_LIBRARY_TYPES, skipping.")
            except Exception:
                print(f"Warning: Library '{name}' not found, skipping.")
        return libraries
    else:
        return [s for s in plex.library.sections() if s.type in type_values]


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
    parser.add_argument("--list-topics", action="store_true",
                        help="Show all available DTDD topic names (for use in INCLUDE_TOPICS/EXCLUDE_TOPICS)")
    args = parser.parse_args()

    dry_run = args.dry_run or getattr(config, "DRY_RUN", False)

    # Handle cache clear
    if args.clear_cache:
        client = DTDDClient(config.DTDD_API_KEY)
        client.clear_cache()
        if not args.clear and not args.movie and not args.list_topics:
            return

    # Handle list-topics: fetch a well-known movie to show all available topics
    if args.list_topics:
        dtdd = DTDDClient(
            api_key=config.DTDD_API_KEY,
            cache_ttl=getattr(config, "CACHE_TTL", 604800),
            api_delay=getattr(config, "API_DELAY", 1.0),
        )
        print("Fetching topic list from DTDD...\n")
        # Search a popular movie likely to have all topics rated
        results = dtdd.search("Avengers Endgame")
        if results:
            media = dtdd.get_media(results[0]["id"])
            stats = media.get("topicItemStats", [])
            topics = sorted(set(
                stat.get("topic", {}).get("name", "")
                for stat in stats
                if stat.get("topic", {}).get("name")
            ))
            print("Available topic names (copy these into INCLUDE_TOPICS or EXCLUDE_TOPICS):\n")
            for topic in topics:
                print(f'    "{topic}",')
            print(f"\n{len(topics)} topics found.")
        else:
            print("Could not fetch topics. Check your DTDD_API_KEY.")
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
    library_types = getattr(config, "PLEX_LIBRARY_TYPES", None)

    # Handle clear mode
    if args.clear:
        clear_warnings(plex, library_names, library_types)
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
        libraries = get_libraries(plex, library_names, library_types)
        print("Libraries to search:")
        for lib in libraries:
            print(f"  - {lib.title}")
        print()
        found = False
        for lib in libraries:
            results = lib.search(title=args.movie)
            for movie in results:
                found = True
                process_movie(dtdd, movie, dry_run=dry_run)
        if not found:
            print(f"Movie '{args.movie}' not found in Plex.")
        return

    # Process all items in configured libraries
    libraries = get_libraries(plex, library_names, library_types)
    if not libraries:
        print("No libraries found to process.")
        sys.exit(1)

    print("Libraries to process:")
    for lib in libraries:
        items = lib.all()
        item_label = "shows" if lib.type == "show" else "movies"
        print(f"  - {lib.title} ({len(items)} {item_label})")
    print()

    total_processed = 0
    total_updated = 0
    start_time = time.time()

    for lib in libraries:
        items = lib.all()
        item_label = "shows" if lib.type == "show" else "movies"
        print(f"\nProcessing: {lib.title} ({len(items)} {item_label})")
        print("-" * 50)

        if lib.type == "show":
            for item in items:
                p, u = process_show(dtdd, item, dry_run=dry_run)
                total_processed += p
                total_updated += u
        else:
            for item in items:
                total_processed += 1
                if process_movie(dtdd, item, dry_run=dry_run):
                    total_updated += 1

    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}")
    print(f"Done in {elapsed:.1f}s")
    print(f"Processed: {total_processed} items")
    print(f"Updated:   {total_updated} items")
    if dry_run:
        print("(DRY RUN — no actual changes made)")


if __name__ == "__main__":
    main()
