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


def matches(text):
    """The listed terms found in `text` (for tests and tuning; never stored or logged)."""
    seq = words(text)
    found = []
    for phrase in terms():
        size = len(phrase)
        if any(tuple(seq[i:i + size]) == phrase for i in range(len(seq) - size + 1)):
            found.append(" ".join(phrase))
    return sorted(found)


def may_be_offensive(text):
    return bool(matches(text))
