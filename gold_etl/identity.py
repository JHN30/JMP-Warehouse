"""Cross-season Gold player and club profiles from Silver."""

from gold_etl.schema import IDENTITY_TABLES
from gold_etl.standings import _dict_rows


PLAYER_FIELDS = ("name", "country_code", "country_name", "height_cm", "weight_kg",
                 "birth_at", "birth_country_code", "birth_country_name",
                 "position", "position_name")
CLUB_FIELDS = ("name", "crest_url", "country_code", "country_name")


def derive_players(registrations):
    """Group player registrations without mixing conflicting Silver identities."""
    codes_by_key = {}
    keys_by_code = {}
    grouped = {}
    for row in registrations:
        key, code = row["person_key"], row["person_code"]
        if not code:
            raise ValueError(f"Silver player {key} in {row['season_code']} has no person_code")
        if (key in codes_by_key and codes_by_key[key] != code or
                code in keys_by_code and keys_by_code[code] != key):
            raise ValueError(f"Silver player identity conflicts for {key}/{code}")
        codes_by_key[key], keys_by_code[code] = code, key
        grouped.setdefault((row["competition_code"], code), []).append(row)

    result = []
    for (competition_code, code), entries in sorted(grouped.items()):
        latest = max(entries, key=lambda row: (row["season_code"], row["registration_key"]))
        seasons = sorted({row["season_code"] for row in entries})
        clubs = {}
        for row in entries:
            if row["club_code"] is not None:
                pair = (row["season_code"], row["club_code"])
                if pair not in clubs or row["registration_key"] > clubs[pair][0]:
                    clubs[pair] = (row["registration_key"], row["club_name"])
        history = [{"seasonCode": season, "clubCode": club,
                    "clubName": clubs[(season, club)][1]}
                   for season, club in sorted(clubs)]
        result.append({"competition_code": competition_code, "person_code": code,
                       **{field: latest[field] for field in PLAYER_FIELDS},
                       "first_season_code": seasons[0],
                       "last_season_code": seasons[-1],
                       "seasons_played": len(seasons), "clubs": history})
    return result


def derive_clubs(clubs):
    grouped = {}
    for row in clubs:
        key = (row["competition_code"], row["club_code"])
        if not key[1]:
            raise ValueError(f"Silver club in {row['season_code']} has no club_code")
        seasons = grouped.setdefault(key, {})
        season = row["season_code"]
        if season in seasons and any(seasons[season][field] != row[field]
                                     for field in CLUB_FIELDS):
            raise ValueError(f"Silver club identity conflicts for {key[1]} in {season}")
        seasons[season] = row
    result = []
    for (competition_code, club_code), seasons in sorted(grouped.items()):
        codes = sorted(seasons)
        latest = seasons[codes[-1]]
        result.append({"competition_code": competition_code, "club_code": club_code,
                       **{field: latest[field] for field in CLUB_FIELDS},
                       "first_season_code": codes[0],
                       "last_season_code": codes[-1],
                       "seasons_played": len(codes)})
    return result


def read_rows(cursor, name, competition_code):
    if name not in IDENTITY_TABLES:
        raise ValueError(f"Unknown Gold identity table: {name}")
    if name == "app_club_identities":
        cursor.execute(
            "SELECT competition_code, season_code, club_code, name, crest_url, "
            "country_code, country_name FROM silver.clubs "
            "WHERE competition_code = %s ORDER BY season_code, club_code",
            (competition_code,))
        return derive_clubs(_dict_rows(cursor))
    cursor.execute(
        "SELECT r.competition_code, r.season_code, r.registration_key, "
        "r.person_key, p.person_code, p.name, p.country_code, p.country_name, "
        "p.height_cm, p.weight_kg, p.birth_at, p.birth_country_code, "
        "p.birth_country_name, r.position, r.position_name, r.club_code, "
        "COALESCE(r.club_name, c.name) AS club_name "
        "FROM silver.registrations AS r LEFT JOIN silver.people AS p "
        "ON p.competition_code = r.competition_code "
        "AND p.season_code = r.season_code AND p.person_key = r.person_key "
        "LEFT JOIN silver.clubs AS c ON c.competition_code = r.competition_code "
        "AND c.season_code = r.season_code AND c.club_code = r.club_code "
        "WHERE r.competition_code = %s AND r.role_code = 'J' "
        "ORDER BY r.season_code, r.person_key, r.registration_key",
        (competition_code,))
    return derive_players(_dict_rows(cursor))
