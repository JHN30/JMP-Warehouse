import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flat_schema import TABLES
from text_clean import (city_name, country_code, country_name, group_name, person_name, position,
                        role_name)


class PersonNameTests(unittest.TestCase):
    def check(self, cases):
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(person_name(source), expected)

    def test_capitals_become_title_case(self):
        self.check([("LARKIN, SHANE", "Larkin, Shane"),
                    ("GÖK, ERDAL", "Gök, Erdal"),
                    ("ALEGBE-ISSIFOU, AL-FAYED", "Alegbe-Issifou, Al-Fayed"),
                    ("AVIV (YUABOV), EFRAIM", "Aviv (Yuabov), Efraim"),
                    ("MICHALOGLOU, a.", "Michaloglou, A."),
                    ("Hernangomez", "Hernangomez")])

    def test_suffixes(self):
        self.check([("BROWN III, JOHN", "Brown III, John"),
                    ("WRIGHT IV, MCKINLEY", "Wright IV, McKinley"),
                    ("BAKER II , ROBERT", "Baker II, Robert"),
                    ("COWAN JR, ANTHONY", "Cowan Jr., Anthony"),
                    ("ALSTON JR. , DERRICK", "Alston Jr., Derrick"),
                    ("HOLDEN, JR", "Holden, Jr."),
                    ("HARRINGTON, JUNIOR", "Harrington, Junior")])

    def test_mc_and_camel_case_names(self):
        self.check([("McCARTY, KELLY", "McCarty, Kelly"),
                    ("MCNAIR, WILLIAM", "McNair, William"),
                    ("MC DUFFIE, MARKIS", "McDuffie, Markis"),
                    ("Mc DADE, RYAN", "McDade, Ryan"),
                    ("COLLINS, DeJUAN", "Collins, DeJuan"),
                    ("KANE, DEANDRE", "Kane, DeAndre"),
                    ("PROFIT, LaRon", "Profit, LaRon"),
                    ("JONES, DEVON", "Jones, Devon"),
                    ("MACON JR, DARYL", "Macon Jr., Daryl")])

    def test_apostrophes(self):
        self.check([("O´BANNON, LARRY", "O'Bannon, Larry"),
                    ("BUTLER, DA´SEAN", "Butler, Da'Sean"),
                    ("ARTEM'EV, GEORGY", "Artem'ev, Georgy"),
                    ("BEN ZE'EV, RONY", "Ben Ze'ev, Rony")])

    def test_initials_and_abbreviations(self):
        self.check([("DOZIER, PJ", "Dozier, PJ"), ("ENGLISH III, AJ", "English III, AJ"),
                    ("BOWMAN, KY", "Bowman, Ky"), ("DICKEY III, JAMES L", "Dickey III, James L"),
                    ("PETROPOULOS, CH.", "Petropoulos, Ch."),
                    ("DR. KARANIS,  GABRIELE", "Dr. Karanis, Gabriele")])

    def test_empty_and_numbers(self):
        self.check([(None, None), ("   ", None), ("45761509L", "45761509L")])


class CityNameTests(unittest.TestCase):
    def test_cities(self):
        for source, expected in [("ISTANBUL", "Istanbul"), ("Istanbul", "Istanbul"),
                                 ("VITORIA-GASTEIZ", "Vitoria-Gasteiz"),
                                 ("Karsıyaka, İzmir", "Karsıyaka, İzmir"),
                                 ("Rishon LeZion", "Rishon LeZion"),
                                 ("St Petersburg", "Saint Petersburg"),
                                 ("Trabzon, Turkey", "Trabzon"), ("BENFICA", "Lisbon"),
                                 (None, None)]:
            with self.subTest(source=source):
                self.assertEqual(city_name(source), expected)


class CodeAndLabelTests(unittest.TestCase):
    def check(self, function, cases):
        for source, expected in cases:
            with self.subTest(function=function.__name__, source=source):
                self.assertEqual(function(source), expected)

    def test_countries(self):
        self.check(country_code, [("UK", "GBR"), ("IVO", "CIV"), ("ZAI", "COD"), ("FYR", "MKD"),
                                  ("LAD", None), ("NAT", None), ("ENG", "ENG"), (None, None)])
        self.check(country_name, [("Cote D’Ivoire", "Ivory Coast"), ("----", "North Macedonia"),
                                  ("Democratic Republic of the Congo (Zaire)",
                                   "Democratic Republic of the Congo"),
                                  ("No country", None), ("Spain", "Spain")])

    def test_group_names(self):
        self.check(group_name, [("Group SEMIFINAL A", "Group Semifinal A"),
                                ("Group Semi-Final 1", "Group Semifinal 1"),
                                ("Group 3RD PLACE GAME", "Group 3rd Place Game"),
                                ("Group Eliminatory VIII", "Group Eliminatory VIII"),
                                ("Group QF A", "Group QF A"), ("Group A", "Group A"),
                                ("Regular Season", "Regular Season"), (None, None)])

    def test_roles_and_positions(self):
        self.check(role_name, [("Unified_Score_Crew", "Unified score crew"),
                               ("Team_Manager", "Team manager"),
                               ("Assitant coach", "Assistant coach"),
                               ("Physical therapist", "Physical therapist"), (None, None)])
        self.check(position, [(-1, None), (0, None), (None, None), (1, 1), (3, 3)])


class SchemaTests(unittest.TestCase):
    def test_cleaned_columns(self):
        cleaned = {(table, field.name): field.clean for table, spec in TABLES.items()
                   for field in spec.fields if field.clean}
        self.assertEqual(cleaned[("clubs", "city")], "city_name")
        for column in [("people", "name"), ("people", "alias"), ("game_player_stats", "person_name"),
                       ("registrations", "person_name"), ("game_team_stats", "coach_name"),
                       ("game_officials", "name"), ("play_by_play", "player_name"),
                       ("shots", "player_name"), ("season_player_stats_misc", "player_name")]:
            self.assertEqual(cleaned[column], "person_name", column)
        self.assertEqual(cleaned[("registrations", "role_name")], "role_name")
        self.assertEqual(cleaned[("registrations", "position")], "position")
        self.assertEqual(cleaned[("game_player_stats", "position")], "position")
        self.assertEqual(cleaned[("games", "group_name")], "group_name")
        self.assertEqual(cleaned[("people", "birth_country_code")], "country_code")
        self.assertEqual(cleaned[("game_officials", "country_name")], "country_name")
        self.assertNotIn(("standings_basic", "position"), cleaned)
        self.assertNotIn(("people", "jersey_name"), cleaned)
        self.assertNotIn(("clubs", "name"), cleaned)


if __name__ == "__main__":
    unittest.main()
