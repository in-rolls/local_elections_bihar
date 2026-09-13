"""Match result rows to candidate-list rows within one seat.

The SEC candidate list is sorted by name and renumbered, while the result feed keeps
its own serial, so in some seats the same serial names different people (39 of
8,062 mukhiya seats). A serial join would move votes and winner flags between
candidates. Matching is by name within the seat, with the serial as a tiebreak.
No maintained transliteration-aware matcher covers these Devanagari spelling
variants, so the rules are kept small and every match records how it was made.
"""

import re
import unicodedata

WINNER = re.compile(r"\s*\(विजेता\)\s*$")
# \u0966 is the Devanagari zero clerks write after abbreviations such as मो.
HONORIFIC = re.compile(
    r"^(?:मो[0Oo\u0966]?|मोहम्मद|मु[0\u0966]|म[0\u0966]|श्रीमती|श्री|बीबी|स्व[0\u0966]|डा[0\u0966]|डॉ[0\u0966]?)\s+"
)
SUFFIX = re.compile(r"\s*\d+$")


def name_key(name):
    """Comparable name: NFC, no winner mark, punctuation, honorific or spaces."""
    text = WINNER.sub("", unicodedata.normalize("NFC", name or ""))
    text = " ".join(text.replace(".", " ").split())
    while HONORIFIC.match(text):
        text = HONORIFIC.sub("", text, count=1)
    return text.replace(" ", "")


def match(candidates, results):
    """Pair candidate serials with result serials for one seat.

    ``candidates`` and ``results`` map serial -> name. Returns
    ``{result_serial: (candidate_serial | None, method)}``, where method is
    ``serial_and_name``, ``name`` (same person at a different serial),
    ``name_contained`` (one remaining candidate's name is contained in the result
    name or vice versa, e.g. an unlisted honorific), ``serial_only`` (same serial,
    names differ and no other candidate matches) or ``result_only`` (no
    candidate-list row). Portal duplicates such as
    "माया देवी 1" match "माया देवी" at the same serial.
    """
    keys = {s: name_key(n) for s, n in candidates.items()}
    pairs, used = {}, set()

    def same(result_name, serial):
        key = name_key(result_name)
        return keys.get(serial) in (key, SUFFIX.sub("", key))

    for serial, name in results.items():
        if serial in keys and same(name, serial):
            pairs[serial] = (serial, "serial_and_name")
            used.add(serial)
    for serial, name in results.items():
        if serial in pairs:
            continue
        options = [s for s in keys if s not in used and same(name, s)]
        if len(options) == 1:
            pairs[serial] = (options[0], "name")
            used.add(options[0])
    for serial, name in results.items():
        if serial in pairs:
            continue
        key = name_key(name)
        options = [
            s
            for s in keys
            if s not in used and keys[s] and (keys[s] in key or key in keys[s])
        ]
        if len(options) == 1:
            pairs[serial] = (options[0], "name_contained")
            used.add(options[0])
    for serial in results:
        if serial in pairs:
            continue
        if serial in keys and serial not in used:
            pairs[serial] = (serial, "serial_only")
            used.add(serial)
        else:
            pairs[serial] = (None, "result_only")
    return pairs
