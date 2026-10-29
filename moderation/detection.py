"""Local, transparent check for possibly offensive messages. No AI, no outside service.

It only decides whether to show the sender "This message may be offensive. Edit or send
anyway?". It never blocks, punishes or reports anyone, and nothing it sees is stored.

Text and listed terms go through the same normalisation, then whole words are compared
(so "class" never matches "ass", and "Scunthorpe" is safe):
  1. Unicode NFC, then remove invisible format characters (zero-width spaces and joiners,
     soft hyphens, BOM: Unicode category Cf).
  2. Case-fold.
  3. Split into words (letters, combining marks and digits, in any script, so Bangla works).
  4. Common l33t swaps inside a word: 0→o 1→i 3→e 4→a 5→s 7→t @→a $→s !→i.
  5. Collapse repeated letters ("idiooot" → "idiot", "haramzaada" → "haramzada").
Disguised spellings: inside one space-separated chunk, symbols between letters are dropped
("i.d.i.o.t" → "idiot") or each stands for one letter ("f*ck" → f?ck). That form only
counts when the WHOLE chunk equals a single listed word of 4+ letters, so "e.g.", "U.S.A.",
version numbers and URLs don't match.
Step 5 means a listed term must not collapse into an ordinary word (e.g. "ass" → "as");
moderation/wordlists/examples.txt keeps such false positives visible in the tests.

The terms live in moderation/wordlists/terms.txt (one term or phrase per line).
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

WORDLIST = Path(__file__).resolve().parent / "wordlists" / "terms.txt"
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
WORD_SYMBOLS = set("@$!")
REPEATS = re.compile(r"(.)\1+")


def normalise(text):
    text = unicodedata.normalize("NFC", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return text.casefold()


def words(text):
    """The normalised words of `text`, in order."""
    out, current = [], []
    for ch in normalise(text):
        if unicodedata.category(ch)[0] in "LMN" or ch in WORD_SYMBOLS:
            current.append(ch)
            continue
        if current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    cleaned = []
    for word in out:
        word = word.strip("!")                 # "idiot!" is "idiot"; "sh!t" keeps its "!"
        if word:
            cleaned.append(REPEATS.sub(r"\1", word.translate(LEET)))
    return cleaned


@lru_cache(maxsize=1)
def terms(path=WORDLIST):
    """Each listed term as a tuple of normalised words. Lines starting with # are comments."""
    found = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            phrase = tuple(words(line))
            if phrase:
                found.add(phrase)
    return frozenset(found)


DISGUISE_MIN_LETTERS = 4


def _is_letter(ch):
    return unicodedata.category(ch)[0] in "LM"


def _disguised(text):
    """(letters-only form, one-symbol-per-letter pattern) for each chunk that hides symbols
    between letters, e.g. "i.d.i.o.t" or "f*ck"."""
    out = []
    for chunk in normalise(text).split():
        chunk = chunk.translate(LEET)
        start, end = 0, len(chunk)
        while start < end and not _is_letter(chunk[start]):
            start += 1
        while end > start and not _is_letter(chunk[end - 1]):
            end -= 1
        core = chunk[start:end]
        if not core or all(_is_letter(ch) for ch in core):
            continue                                    # plain words are handled by words()
        # Collapse repeated letters like the listed words are ("bullsh*t" → "bulsh*t"); each
        # symbol stays one wildcard ("f**k" → f..k).
        squashed = "".join(ch for i, ch in enumerate(core)
                           if not (_is_letter(ch) and i and core[i - 1] == ch))
        letters = REPEATS.sub(r"", "".join(ch for ch in core if _is_letter(ch)))
        pattern = "".join(re.escape(ch) if _is_letter(ch) else "." for ch in squashed)
        out.append((letters, re.compile(pattern)))
    return out


@lru_cache(maxsize=1)
def _single_words():
    return frozenset(p[0] for p in terms() if len(p) == 1 and len(p[0]) >= DISGUISE_MIN_LETTERS)


def matches(text):
    """The listed terms found in `text` (for tests and tuning; never stored or logged)."""
    seq = words(text)
    found = set()
    for phrase in terms():
        size = len(phrase)
        if any(tuple(seq[i:i + size]) == phrase for i in range(len(seq) - size + 1)):
            found.add(" ".join(phrase))
    long_words = _single_words()
    for letters, pattern in _disguised(text):
        if letters in long_words:
            found.add(letters)
        found.update(word for word in long_words if pattern.fullmatch(word))
    return sorted(found)


def may_be_offensive(text):
    return bool(matches(text))
