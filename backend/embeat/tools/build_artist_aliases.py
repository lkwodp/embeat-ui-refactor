from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from artist_aliases import (  # noqa: E402
    load_curated_aliases,
    load_musicbrainz_aliases,
    merge_artist_alias_sources,
    normalize_artist_key,
)

try:
    from zhconv import convert as zh_convert
except ImportError:
    zh_convert = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge curated artist aliases with the optional MusicBrainz lookup database."
    )
    parser.add_argument(
        "--curated",
        type=Path,
        default=APP_DIR / "data" / "chinese_singers_extended.json",
        help="Human-maintained JSON file. Its values always win conflicts.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=APP_DIR / "data" / "mb_lookup.db",
        help="MusicBrainz lookup SQLite database.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=APP_DIR / "data" / "chinese_singers_generated.json",
        help="Generated merged JSON file. The curated input is never overwritten.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    curated_path = args.curated.resolve()
    database_path = args.database.resolve()
    output_path = args.output.resolve()
    if output_path == curated_path:
        raise SystemExit("Refusing to overwrite the curated alias file; choose another --output path.")

    curated = load_curated_aliases(curated_path)
    musicbrainz = load_musicbrainz_aliases(
        database_path,
        lambda value: zh_convert(value, locale="zh-cn") if zh_convert else value,
    )
    curated_by_key = {normalize_artist_key(name): value for name, value in curated.items()}
    conflicts = sum(
        1
        for name, value in musicbrainz.items()
        if normalize_artist_key(name) in curated_by_key
        and curated_by_key[normalize_artist_key(name)] != value
    )
    merged = merge_artist_alias_sources((curated,), (musicbrainz,))
    added = len(merged) - len(curated_by_key)
    records = [
        {"chinese": chinese, "english": english}
        for english, chinese in sorted(
            merged.items(),
            key=lambda item: (normalize_artist_key(item[0]), item[0]),
        )
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Curated aliases: {len(curated_by_key)}")
    print(f"MusicBrainz candidates: {len(musicbrainz)}")
    print(f"MusicBrainz additions: {added}")
    print(f"Conflicts kept from curated JSON: {conflicts}")
    print(f"Merged aliases written: {len(records)} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
