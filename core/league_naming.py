"""Canonical normalization of league names for cross-platform matching.

Different bookmakers write the same league very differently:
"USA. USL League Two" vs "Estados Unidos · USL League 2". A pure fuzzy string
ratio misses these. Instead we normalize to a canonical token set first
(country aliases, number words/roman → digits, separators, token canon), while
PRESERVING the discriminators that must NOT be merged: gender (women) and age
(U20/U23). Two names with the same canonical form are the same league.
"""

from __future__ import annotations

import re
import unicodedata

# Country / region aliases → a single canonical token. Multi-word phrases are
# matched as whole words before tokenizing. Extend freely.
_COUNTRY_ALIASES: dict[str, str] = {
    "estados unidos": "usa",
    "united states": "usa",
    "eeuu": "usa",
    "ee uu": "usa",
    "us": "usa",
    "usa": "usa",
    "inglaterra": "england",
    "england": "england",
    "brasil": "brazil",
    "brazil": "brazil",
    "alemania": "germany",
    "germany": "germany",
    "espana": "spain",
    "spain": "spain",
    "italia": "italy",
    "italy": "italy",
    "francia": "france",
    "france": "france",
    "paises bajos": "netherlands",
    "holanda": "netherlands",
    "netherlands": "netherlands",
    "noruega": "norway",
    "norway": "norway",
    "suecia": "sweden",
    "sweden": "sweden",
    "finlandia": "finland",
    "finland": "finland",
    "rumania": "romania",
    "rumanía": "romania",
    "romania": "romania",
    "eslovaquia": "slovakia",
    "slovakia": "slovakia",
    "argelia": "algeria",
    "algeria": "algeria",
    "islandia": "iceland",
    "iceland": "iceland",
    "dinamarca": "denmark",
    "denmark": "denmark",
    "polonia": "poland",
    "poland": "poland",
    "grecia": "greece",
    "greece": "greece",
    "turquia": "turkey",
    "turquía": "turkey",
    "turkey": "turkey",
    "japon": "japan",
    "japón": "japan",
    "japan": "japan",
    "lituania": "lithuania",
    "lithuania": "lithuania",
    "croacia": "croatia",
    "croatia": "croatia",
    "serbia": "serbia",
    "bosnia": "bosnia",
    "bosnia-herzegovina": "bosnia",
    "bosnia and herzegovina": "bosnia",
}

# Number words (en + es) and roman numerals → digit string.
_NUMBER_WORDS: dict[str, str] = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
    "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
    "primera": "1", "segunda": "2", "tercera": "3", "cuarta": "4", "quinta": "5",
    "first": "1", "second": "2", "third": "3",
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
    "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
    "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16", "xvii": "17", "xviii": "18", "xix": "19", "xx": "20",
}

# Token canonicalization (synonyms → one form). Discriminators (women/age) live here too.
_TOKEN_ALIASES: dict[str, str] = {
    "liga": "league",
    "league": "league",
    "championship": "league",
    "campeonato": "league",
    "division": "div",
    "división": "div",
    "femenino": "women", "femenina": "women", "women": "women", "woman": "women",
    "damas": "women", "dam": "women", "mujeres": "women", "féminas": "women", "feminas": "women",
    "f": "women", "w": "women", 'femenil': "women", "fem": "women",
    "sub": "u", "u": "u", "juvenil": "youth", "youth": "youth", "reserva": "reserves", "reserves": "reserves", "res": "reserves"
}

# Tokens dropped as noise (incl. men markers → treat unmarked as men).
_STOPWORDS: set[str] = {
    "the", "de", "del", "la", "el", "los", "las",
    "masculino", "masculina", "men", "man", "herr", "varones", "m",
}

_ROMAN_RE = re.compile(r"^[ivxlcdm]+$")
_AGE_RE = re.compile(r"^(?:u|sub)(\d{1,2})$")


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _apply_country_aliases(text: str) -> str:
    for phrase, canon in sorted(_COUNTRY_ALIASES.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{re.escape(phrase)}\b", canon, text)
    return text


def normalize_league_name(name: str | None) -> str:
    """Return a canonical, order-insensitive token string for a league name."""

    if not name:
        return ""
    s = _strip_accents(str(name).lower())
    s = re.sub(r"[·.\-_/|,:()\[\]]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _apply_country_aliases(s)

    raw_tokens = s.split()
    tokens: list[str] = []
    i = 0
    while i < len(raw_tokens):
        t = raw_tokens[i]
        # "sub 23" / "u 23" -> "u23"
        if t in ("u", "sub") and i + 1 < len(raw_tokens) and raw_tokens[i + 1].isdigit():
            tokens.append(f"u{raw_tokens[i + 1]}")
            i += 2
            continue
        age = _AGE_RE.match(t)
        if age:
            tokens.append(f"u{age.group(1)}")
            i += 1
            continue
        # number word / roman -> digit
        if t in _NUMBER_WORDS:
            t = _NUMBER_WORDS[t]
        elif _ROMAN_RE.match(t) and t in _NUMBER_WORDS:
            t = _NUMBER_WORDS[t]
        t = _TOKEN_ALIASES.get(t, t)
        if t in _STOPWORDS or not t:
            i += 1
            continue
        tokens.append(t)
        i += 1

    # order-insensitive canonical key (dedup + sort)
    return " ".join(sorted(set(tokens)))


def same_league(a: str | None, b: str | None) -> bool:
    """True when two names share the same canonical form (and it's non-empty)."""

    na = normalize_league_name(a)
    return bool(na) and na == normalize_league_name(b)


def anagram_key(name: str | None) -> str:
    """Order-free fingerprint: the canonical form with spaces dropped, chars sorted.

    Built on top of :func:`normalize_league_name`, so it inherits the canonical
    aliases AND the discriminators (women / U20 produce different characters, so
    they never share an anagram key). Catches equivalences that differ only by
    word/character order or spacing ("NPL League" vs "League NPL").
    """

    canonical = normalize_league_name(name)
    return "".join(sorted(canonical.replace(" ", "")))


def same_league_anagram(a: str | None, b: str | None) -> bool:
    """True when two names share a non-empty anagram key."""

    ka = anagram_key(a)
    return bool(ka) and ka == anagram_key(b)


_CANONICAL_COUNTRIES: set[str] = set(_COUNTRY_ALIASES.values())


def league_slug(name: str | None, max_length: int = 60) -> str:
    """Public, stable slug for a league name ("USA. WPSL (F)" -> "usa-wpsl-f").

    Word order is preserved (unlike :func:`normalize_league_name`) because the
    slug is an identifier shown to users; once assigned it must never change.
    """

    if not name:
        return ""
    s = _strip_accents(str(name).lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:max_length].rstrip("-")


def extract_league_traits(name: str | None) -> dict[str, str | None]:
    """Best-effort country / gender / age_group from a league name.

    Gender is "F" only when a women marker is present (unmarked == men == None,
    matching the normalize convention). Age is the first U<NN> marker ("U20").
    Country is the canonical alias token when one appears in the name.
    """

    tokens = normalize_league_name(name).split()
    country = next((t for t in tokens if t in _CANONICAL_COUNTRIES), None)
    gender = "F" if "women" in tokens else None
    age = next((t for t in tokens if _AGE_RE.match(t)), None)
    return {
        "country": country,
        "gender": gender,
        "age_group": age.upper() if age else None,
    }


from difflib import SequenceMatcher

_LEAGUE_SIMILARITY_TRANSLATION_MAP: dict[str, str] = {
    "alemania": "germany",
    "espana": "spain",
    "inglaterra": "england",
    "italia": "italy",
    "francia": "france",
    "occidental": "western",
    "oriental": "eastern",
    "sur": "south",
    "norte": "north",
    "central": "central",
    "copa": "cup",
    "liga": "league",
    "campeonato": "championship",
    "division": "division",
    "primera": "premier",
    "segunda": "second",
    "tercera": "third",
    "sub": "u",
    "juvenil": "youth",
    "reserva": "reserves",
    "reservas": "reserves",
    "femenino": "women",
    "femenil": "women",
    "mujeres": "women",
    "fem": "women",
    "nueva": "new",
    "gales": "wales",
    "australia": "australia",
}

_LEAGUE_SIMILARITY_STOPWORDS: set[str] = {"de", "la", "el", "del", "y", "a", "of", "and", "the", "in", "for", "fc", "club"}


def league_name_similarity(left: str, right: str) -> float:
    """Loose similarity between two league names, ignoring case, prepositions, and translating Spanish terms to English."""
    if not left or not right:
        return 0.0

    def norm(value: str) -> str:
        # Strip accents
        folded = "".join(c for c in unicodedata.normalize('NFD', value) if unicodedata.category(c) != 'Mn')
        folded = folded.lower()
        # Normalize sub-XX or u-XX to uXX
        folded = re.sub(r"\b(sub|u)-?(\d+)\b", r"u\2", folded)
        cleaned = re.sub(r"[^a-z0-9]+", " ", folded).strip()
        cleaned = _apply_country_aliases(cleaned)
        tokens = cleaned.split()
        translated = [
            _LEAGUE_SIMILARITY_TRANSLATION_MAP.get(t, t)
            for t in tokens
            if t not in _LEAGUE_SIMILARITY_STOPWORDS
        ]
        return " ".join(translated)

    left_norm = norm(left)
    right_norm = norm(right)
    ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return ratio
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return max(ratio, overlap)


_TEAM_TRANSLATION_MAP = {
    "femenino": "women",
    "femenil": "women",
    "mujeres": "women",
    "fem": "women",
    "reserva": "reserves",
    "reservas": "reserves",
    "sub": "u",
    "youth": "youth",
    "juvenil": "youth",
}

_TEAM_STOPWORDS = {
    "fc", "afc", "sc", "cf", "ca", "ac", "if", "sk", "club", "de", "the",
    "women", "w", "u20", "u23", "u19", "u17", "reserves", "reserva", "reservas",
    "femenino", "femenil", "sub", "fem", "youth", "u21", "u18", "u16", "u15"
}


def normalize_team_name(value: str) -> str:
    """Normalize a team name to a canonical, space-separated format."""
    raw = unicodedata.normalize("NFKD", str(value or "").lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"\bsub[- ]?(\d+)\b", r"u\1", raw)
    tokens = raw.split()
    translated = [_TEAM_TRANSLATION_MAP.get(t, t) for t in tokens]
    raw = " ".join(translated)
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def team_name_similarity(left: str, right: str) -> float:
    """Fuzzy similarity between two team names, handling common synonyms and stopwords."""
    if not left or not right:
        return 0.0

    left_norm, right_norm = normalize_team_name(left), normalize_team_name(right)
    if not left_norm or not right_norm:
        return 0.0
    ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    lt = set(left_norm.split()) - _TEAM_STOPWORDS
    rt = set(right_norm.split()) - _TEAM_STOPWORDS
    if lt and rt:
        overlap = len(lt & rt) / min(len(lt), len(rt))
        return max(ratio, overlap)
    return ratio
