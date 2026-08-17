from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Iterable


Simplifier = Callable[[str], str]


@dataclass(frozen=True)
class TitleProfile:
    original: str
    variants: tuple[str, ...]
    components: tuple[str, ...]
    is_medley: bool


_BRACKET_RE = re.compile(r"\s*[\(（\[【][^\)）\]】]*[\)）\]】]\s*")
_MEDLEY_PREFIX_RE = re.compile(r"^\s*(?:medley|mashup|串烧|串燒|组曲|組曲|联唱|聯唱)\s*[:：\-–—]?\s*", re.I)
_EXPLICIT_COMPONENT_RE = re.compile(r"\s*(?:\+|/|／|、|\||;|；|＆|&)\s*")
_SPACED_DASH_RE = re.compile(r"\s+[-‐‑‒–—－]\s+")
_DASH_SEPARATOR_RE = re.compile(r"[-‐‑‒–—―－~〜～]+")
_VERSION_SUFFIX_RE = re.compile(
    r"^(?:live(?:\s+(?:at|in|from)\b.*)?|现场(?:版|录音)?|現場(?:版|錄音)?|演唱会(?:版)?|演唱會(?:版)?|"
    r"remaster(?:ed)?(?:\s+\d{2,4})?|remix|mix|acoustic|unplugged|demo|radio\s+edit|edit|instrumental|"
    r"inst\.?|伴奏|纯音乐|純音樂|钢琴版|鋼琴版|吉他版|清唱版|录音室版|錄音室版)$",
    re.I,
)
_MEDIA_SUFFIX_RE = re.compile(
    r"(?:主题曲|主題曲|片尾曲|片头曲|片頭曲|插曲|推广曲|推廣曲|宣传曲|宣傳曲|概念曲|角色曲|原声|原聲|ost)\s*$",
    re.I,
)
_VERSION_PATTERNS = {
    "live": re.compile(r"\blive\b|现场|現場|演唱会|演唱會", re.I),
    "remix": re.compile(r"\bremix\b|混音版", re.I),
    "remaster": re.compile(r"\bremaster(?:ed)?\b|重制版|重製版", re.I),
    "acoustic": re.compile(r"\bacoustic\b|\bunplugged\b|不插电|不插電", re.I),
    "instrumental": re.compile(r"\binstrumental\b|\binst\.?\b|伴奏|纯音乐|純音樂", re.I),
    "demo": re.compile(r"\bdemo\b|样带|樣帶", re.I),
}

# Spotify metadata occasionally mixes simplified Chinese glyphs into Japanese
# titles. Search APIs are less forgiving than the scorer, so keep a small set
# of high-confidence spelling equivalents for both query generation and match
# normalization.
_SEARCH_EQUIVALENT_GROUPS = (
    ("间", "間"),
    ("终", "終"),
    ("暝", "瞑"),
)
_MATCH_EQUIVALENTS = str.maketrans({"間": "间", "終": "终", "暝": "瞑"})

# Streaming metadata frequently exposes Korean releases with an English title
# and romanized artist, while NetEase and KuGou index the same recording under
# Korean or Chinese-transliterated metadata. Keep aliases grouped so search and
# scoring can use every spelling without weakening the confidence threshold.
_ARTIST_ALIAS_GROUPS = (
    ("Ha Yea Song", "Song Haye", "송하예", "宋荷艺"),
    ("Kassy", "케이시"),
    ("Sin Ye Young", "신예영"),
    ("BUMKEY", "Bumkey", "범키"),
    ("Park Hyungsik", "Park Hyung Sik", "박형식", "朴炯植"),
    ("Han Dong Geun", "한동근", "韩东根"),
    ("Lee Yejoon", "Lee Ye Joon", "이예준", "李艺俊"),
    ("LEE HONG GI", "Lee Hong Gi", "Lee Hongki", "이홍기", "李洪基"),
    ("Sung Si Kyung", "성시경", "成始璄"),
)

_TRACK_TITLE_ALIAS_GROUPS = (
    (("Ha Yea Song",), ("Your Regards", "니 소식")),
    (("Ha Yea Song",), ("After the day", "그 날 이후")),
    (("Kassy",), ("You're a good love", "넌 참 좋은 사람이었어")),
    (("Kassy",), ("Broke Up Today (2024)", "오늘 헤어졌어요 (2024)", "오늘 헤어졌어요")),
    (("BUMKEY",), ("Rain & You", "비 그리고 너")),
    (("Park Hyungsik",), ("Because of You", "그 사람이 너라서")),
    (("Han Dong Geun",), ("Still, I love you", "그래도 사랑합니다")),
    (("Lee Yejoon",), ("Everyday waiting you", "니 번호가 뜨는 일")),
    (("Lee Yejoon",), ("Again (Prod.V.O.S)", "다시 만날까 봐 (Prod.V.O.S)", "다시 만날까 봐")),
    (("Lee Yejoon",), ("On That Day", "그날에 나는 맘이 편했을까")),
    (("Sin Ye Young",), ("Last Love", "마지막 사랑")),
    (("Sin Ye Young",), ("I think you're not missing me", "넌 내가 보고 싶지 않나 봐")),
    (("LEE HONG GI",), ("Still love you", "사랑했었다 (Still love you)", "사랑했었다")),
    (("Sung Si Kyung",), ("Moments in-between", "이음새")),
)


def tidy_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = tidy_text(value).strip(" -:：")
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _strip_trailing_descriptors(value: str) -> str:
    text = tidy_text(value)
    for _ in range(4):
        parts = _SPACED_DASH_RE.split(text)
        if len(parts) < 2:
            break
        suffix = parts[-1].strip()
        if not (_VERSION_SUFFIX_RE.search(suffix) or _MEDIA_SUFFIX_RE.search(suffix)):
            break
        text = " - ".join(parts[:-1]).strip()
    return text


def _medley_components(value: str, has_prefix: bool) -> list[str]:
    explicit = _EXPLICIT_COMPONENT_RE.split(value)
    if len(explicit) >= 2:
        return _dedupe(explicit)
    if has_prefix:
        tokens = [item for item in re.split(r"\s+", value) if item]
        if len(tokens) >= 2 and all(re.search(r"[\u3400-\u9fff]", token) for token in tokens):
            return _dedupe(tokens)
    return []


def _dash_fragments(value: str) -> list[str]:
    parts = _dedupe(_DASH_SEPARATOR_RE.split(value))
    if len(parts) < 2 or len(parts) > 4:
        return []
    return [
        part for part in parts
        if len(normalize_match_text(part)) >= 2 and not _VERSION_SUFFIX_RE.fullmatch(part)
    ]


def _orthographic_variants(value: str, limit: int = 8) -> list[str]:
    variants = [tidy_text(value)]
    for group in _SEARCH_EQUIVALENT_GROUPS:
        snapshot = list(variants)
        for item in snapshot:
            if not any(glyph in item for glyph in group):
                continue
            for target in group:
                variant = item
                for glyph in group:
                    variant = variant.replace(glyph, target)
                variants.append(variant)
        variants = _dedupe(variants)[:limit]
    return variants


def build_title_profile(value: str) -> TitleProfile:
    original = tidy_text(value)
    without_suffix = _strip_trailing_descriptors(original)
    without_brackets = tidy_text(_BRACKET_RE.sub(" ", without_suffix))
    prefix_match = _MEDLEY_PREFIX_RE.match(without_brackets)
    is_prefixed_medley = bool(prefix_match)
    body = _MEDLEY_PREFIX_RE.sub("", without_brackets, count=1).strip() if is_prefixed_medley else without_brackets
    components = _medley_components(body, is_prefixed_medley)
    is_medley = is_prefixed_medley or len(components) >= 2

    preferred: list[str] = []
    if len(components) >= 2:
        preferred.extend((" + ".join(components), " / ".join(components), " ".join(components)))
    dash_fragments = _dash_fragments(body)
    if len(dash_fragments) >= 2:
        preferred.extend((" ".join(dash_fragments), *dash_fragments))
    preferred.extend((body, without_brackets, without_suffix, original, tidy_text(_BRACKET_RE.sub(" ", original))))
    return TitleProfile(original=original, variants=tuple(_dedupe(preferred)), components=tuple(components), is_medley=is_medley)


def title_search_variants(*values: str, limit: int = 8) -> list[str]:
    variants: list[str] = []
    for value in values:
        for candidate in build_title_profile(value).variants:
            variants.extend(_orthographic_variants(candidate, limit=limit))
    return _dedupe(variants)[:limit]


def normalize_match_text(value: str, to_simplified: Simplifier | None = None) -> str:
    text = tidy_text(value)
    if to_simplified:
        text = to_simplified(text)
    text = text.translate(_MATCH_EQUIVALENTS)
    return re.sub(r"[^\w\u3400-\u9fff]+", "", text.casefold())


def artist_search_aliases(*values: str) -> list[str]:
    """Return equivalent platform spellings for one or more artist names."""
    keys = {normalize_match_text(value) for value in values if tidy_text(value)}
    aliases: list[str] = []
    for group in _ARTIST_ALIAS_GROUPS:
        group_keys = {normalize_match_text(value) for value in group}
        if keys & group_keys:
            aliases.extend(group)
    return _dedupe(aliases)


def track_title_aliases(input_titles: Iterable[str], input_artists: Iterable[str]) -> list[str]:
    """Return title translations scoped to the matching artist.

    Artist scoping is important for generic titles such as "Because of You" and
    "Last Love", which otherwise produce many unrelated exact-title results.
    """
    title_keys = {normalize_match_text(value) for value in input_titles if tidy_text(value)}
    artist_keys = {normalize_match_text(value) for value in input_artists if tidy_text(value)}
    aliases: list[str] = []
    for artist_names, title_names in _TRACK_TITLE_ALIAS_GROUPS:
        accepted_artist_keys = {
            normalize_match_text(alias)
            for artist_name in artist_names
            for alias in artist_search_aliases(artist_name)
        }
        accepted_title_keys = {normalize_match_text(value) for value in title_names}
        if artist_keys & accepted_artist_keys and title_keys & accepted_title_keys:
            aliases.extend(title_names)
    return [value for value in _dedupe(aliases) if normalize_match_text(value) not in title_keys]


def _text_similarity(left: str, right: str, to_simplified: Simplifier | None = None) -> float:
    left_norm = normalize_match_text(left, to_simplified)
    right_norm = normalize_match_text(right, to_simplified)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    best = SequenceMatcher(None, left_norm, right_norm).ratio()
    if left_norm in right_norm or right_norm in left_norm:
        coverage = min(len(left_norm), len(right_norm)) / max(len(left_norm), len(right_norm))
        best = max(best, coverage * 0.96)
    return best


def best_title_similarity(
    input_titles: Iterable[str],
    candidate_titles: Iterable[str],
    to_simplified: Simplifier | None = None,
) -> float:
    left_profiles = [build_title_profile(value) for value in input_titles if tidy_text(value)]
    right_profiles = [build_title_profile(value) for value in candidate_titles if tidy_text(value)]
    best = 0.0
    for left in left_profiles:
        for right in right_profiles:
            for left_variant in left.variants:
                for right_variant in right.variants:
                    best = max(best, _text_similarity(left_variant, right_variant, to_simplified))

    # An ampersand can be part of an ordinary translated title (for example
    # "Rain & You"). If another supplied alias is a plain title, an exact match
    # against that alias must not be capped by the medley coverage rule.
    medleys = [profile for profile in left_profiles if profile.is_medley and len(profile.components) >= 2]
    if medleys and any(not profile.is_medley for profile in left_profiles):
        medleys = []
    if medleys:
        candidate_norms = [
            normalize_match_text(variant, to_simplified)
            for profile in right_profiles
            for variant in profile.variants
        ]
        coverage = 0.0
        for profile in medleys:
            components = [normalize_match_text(item, to_simplified) for item in profile.components]
            matched = sum(1 for component in components if component and any(component in candidate for candidate in candidate_norms))
            coverage = max(coverage, matched / max(len(components), 1))
        if coverage >= 1.0:
            best = max(best, 0.98)
        elif coverage >= 0.75:
            best = max(best, 0.84)
        else:
            best = min(best, 0.59)
    return best


def best_artist_similarity(
    input_artists: Iterable[str],
    candidate_artists: Iterable[str],
    to_simplified: Simplifier | None = None,
) -> float:
    best = 0.0
    for left in input_artists:
        for right in candidate_artists:
            left_norm = normalize_match_text(left, to_simplified)
            right_norm = normalize_match_text(right, to_simplified)
            if not left_norm or not right_norm:
                continue
            if left_norm == right_norm:
                return 1.0
            if left_norm in right_norm or right_norm in left_norm:
                shorter = left_norm if len(left_norm) <= len(right_norm) else right_norm
                has_cjk = bool(re.search(r"[\u3400-\u9fff]", shorter))
                if (has_cjk and len(shorter) >= 2) or (not has_cjk and len(shorter) >= 4):
                    best = max(best, 0.92)
            best = max(best, _text_similarity(left, right, to_simplified))
    return best


def version_tags(*values: str) -> set[str]:
    text = " ".join(tidy_text(value) for value in values if value)
    return {name for name, pattern in _VERSION_PATTERNS.items() if pattern.search(text)}


def combined_match_score(title_score: float, artist_score: float, requested_versions: set[str], candidate_versions: set[str]) -> tuple[float, int]:
    score = title_score * 0.82 + artist_score * 0.18
    version_match = int(bool(requested_versions & candidate_versions)) if requested_versions else 0
    if title_score >= 0.98 and artist_score >= 0.72:
        score = max(score, 0.86 + artist_score * 0.14)
    if requested_versions:
        score += 0.035 if version_match else -0.035
    elif candidate_versions:
        score -= 0.025
    return max(0.0, min(score, 1.0)), version_match


def confident_match(title_score: float, artist_score: float, score: float, artist_required: bool = True) -> bool:
    if title_score < 0.64 or score < 0.68:
        return False
    if not artist_required:
        return True
    if title_score >= 0.96:
        return artist_score >= 0.72
    if title_score >= 0.84:
        return artist_score >= 0.68
    return artist_score >= 0.86
