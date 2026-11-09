"""Display forms for Silver text columns.

The API sends person names in capitals ("BROWN III, JOHN"), club cities and
group names in mixed styles ("ISTANBUL", "Istanbul") and some codes in two
spellings ("UK", "GBR"). The loader stores one form; Bronze keeps the exact
source values. flat_schema.py names the function for each column.
"""

import re

# Given names the source writes in camel case in some feeds ("COLLINS, DeJUAN").
# The same names in capitals get the same form, so every feed agrees.
CAMEL_NAMES = {name.upper(): name for name in (
    "DeAndre", "DeAngelo", "DeJuan", "DeJulius", "DeMarcus", "DeQuan", "Da'Sean", "LaRon",
)}
ROMAN_NUMERALS = {"II", "III", "IV"}
# Written with a period: "DAVIS JR, COREY" -> "Davis Jr., Corey".
ABBREVIATIONS = {"JR": "Jr", "DR": "Dr", "CH": "Ch"}
# "O'BANNON" -> "O'Bannon", "DA'SEAN" -> "Da'Sean"; other apostrophes are inside a
# transliterated name: "ARTEM'EV" -> "Artem'ev", "ZE'EV" -> "Ze'ev".
APOSTROPHE_PREFIXES = {"O", "D", "L", "DA", "DE", "DI", "LA", "LE"}
VOWELS = set("AEIOUY")

# Source city values that are a duplicate spelling, a club name or carry the country.
CITY_NAMES = {
    "St Petersburg": "Saint Petersburg",
    "Nizhni Nóvgorod": "Nizhny Novgorod",
    "Trabzon, Turkey": "Trabzon",
    "Benfica": "Lisbon",
    "Ovarense": "Ovar",
    "Kalev": "Tallinn",
    "Dunkerke": "Gravelines",
}

# One code and name per country; the first of each pair is in current seasons.
# None marks values that are not a country.
COUNTRY_CODES = {"IVO": "CIV", "ZAI": "COD", "UK": "GBR", "FYR": "MKD", "LAD": None, "NAT": None}
COUNTRY_NAMES = {
    "Cote D’Ivoire": "Ivory Coast",
    "Democratic Republic of the Congo (Zaire)": "Democratic Republic of the Congo",
    "----": "North Macedonia",  # code FYR
    "Adriatic League": None,
    "No country": None,
}
ROLE_NAMES = {"Assitant coach": "Assistant coach"}

WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")


def lower(text):
    # "İ".lower() is "i" plus a combining dot.
    return text.lower().replace("i̇", "i")


def capitalized(text):
    return text[:1].upper() + lower(text[1:])


def from_mixed_case(word):
    """Keep the source's lower-case letters and the first capital of each run:
    "McCARTY" -> "McCarty", "DeMARCUS" -> "DeMarcus"."""
    return "".join(lower(char) if index and word[index - 1].isupper() and char.isupper()
                   else char for index, char in enumerate(word))


def name_word(word):
    upper = word.upper()
    if upper in CAMEL_NAMES:
        return CAMEL_NAMES[upper]
    if upper in ABBREVIATIONS:
        return ABBREVIATIONS[upper]
    if not (word.isupper() or word.islower()):
        return from_mixed_case(word)
    if upper in ROMAN_NUMERALS:
        return upper
    if len(upper) == 2 and (not VOWELS & set(upper) or upper.endswith("J")):
        return upper  # initials: PJ, TJ, KC, AJ
    if upper.startswith("MC") and len(upper) > 3:
        return "Mc" + capitalized(word[2:])
    head, *rest = word.split("'")
    parts = [capitalized(head)]
    for part in rest:
        parts.append(capitalized(part) if head.upper() in APOSTROPHE_PREFIXES else lower(part))
        head = part
    return "'".join(parts)


def tidy(value):
    text = re.sub(r"\s+", " ", str(value))
    return re.sub(r"\s*,\s*", ", ", text).strip()


def person_name(value):
    """ "BROWN III, JOHN" -> "Brown III, John"; "DAVIS JR , COREY" ->
    "Davis Jr., Corey"; "MC DADE, RYAN" -> "McDade, Ryan"."""
    if value is None:
        return None
    text = tidy(re.sub("[´`’]", "'", str(value)))
    if not text or any(char.isdigit() for char in text):
        return text or None  # a passport number, not a name
    text = re.sub(r"\b(Mc|MC) (?=[^\W\d_]{2})", "Mc", text)
    text = WORD.sub(lambda match: name_word(match.group()), text)
    return re.sub(r"\b(Jr|Dr|Ch)\b(?!\.)", r"\1.", text)


def city_name(value):
    """ "ISTANBUL" -> "Istanbul"; mixed-case values keep their spelling."""
    if value is None:
        return None
    text = tidy(value)
    if text and not any(char.islower() for char in text):
        text = WORD.sub(lambda match: capitalized(match.group()), text)
    return CITY_NAMES.get(text, text) or None


def group_name(value):
    """ "Group SEMIFINAL A" -> "Group Semifinal A"; "Group 3RD PLACE GAME" ->
    "Group 3rd Place Game"; letters, roman numerals and "QF" stay."""
    if value is None:
        return None
    text = tidy(value).replace("Semi-Final", "Semifinal")

    def word(match):
        word = match.group()
        if len(word) < 3 or re.fullmatch(r"[IVX]+", word) or not word.isupper():
            return word
        return capitalized(word)

    text = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", lambda match: match.group(1) + lower(match.group(2)), text)
    return WORD.sub(word, text) or None


def country_code(value):
    return COUNTRY_CODES.get(value, value)


def country_name(value):
    return COUNTRY_NAMES.get(value, value)


def role_name(value):
    """ "Unified_Score_Crew" -> "Unified score crew", like "Physical therapist"."""
    if value is None:
        return None
    text = capitalized(tidy(value.replace("_", " ")))
    return ROLE_NAMES.get(text, text) or None


def position(value):
    """Playing position 1-3 (guard, forward, center); the source's -1 and 0 mean none."""
    return value if value is not None and value > 0 else None
