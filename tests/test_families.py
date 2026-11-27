import unittest

from weave.families import clean_tags, color_of, family_of, family_of_list, order_of

CASES = {"hard rock": "Rock", "rock urbano": "Rock", "folk rock": "Rock", "blues rock": "Rock", "dance-pop": "Pop",
         "neoclassical metal": "Metal", "baroque": "Clásica / Bandas sonoras", "soundtrack": "Clásica / Bandas sonoras",
         "film score": "Clásica / Bandas sonoras", "post-punk": "Rock", "singer-songwriter": "Folk / Cantautor",
         "cantautor": "Folk / Cantautor", "country": "Folk / Cantautor", "flamenco": "Latina / Flamenco",
         "r&b": "Soul / Funk / Jazz / Blues", "synth-pop": "Electrónica", "trap latino": "Hip hop", "sin género": "Otros"}


class FamiliesTest(unittest.TestCase):
    def test_family_of_cases(self):
        for genre, fam in CASES.items():
            with self.subTest(genre=genre):
                self.assertEqual(family_of(genre), fam)

    def test_family_of_list_skips_otros(self):
        self.assertEqual(family_of_list(["spanish", "rock"]), "Rock")
        self.assertEqual(family_of_list(["spanish"]), "Otros")
        self.assertEqual(family_of_list([]), "Otros")

    def test_colors_and_order(self):
        self.assertEqual(color_of("Rock"), "#ff2e88")
        self.assertEqual(color_of("Otros"), "#b09cc0")
        self.assertEqual(order_of("Metal"), 0)
        self.assertEqual(order_of("Otros"), 9)

    def test_clean_tags_drops_non_genres(self):
        tags = [("rock", 100), ("Spanish Rock", 82), ("Rock Urbano", 35), ("spanish", 23), ("marea", 5), ("seen live", 40)]
        self.assertEqual(clean_tags(tags, "Marea"), [("rock", 100), ("spanish rock", 82), ("rock urbano", 35)])

    def test_clean_tags_drops_artist_name_and_caps_at_five(self):
        tags = [("Extremoduro", 100)] + [(g, 90 - i) for i, g in enumerate(["rock", "hard rock", "punk", "blues", "folk", "pop"])]
        self.assertEqual([t for t, _ in clean_tags(tags, "Extremoduro")], ["rock", "hard rock", "punk", "blues", "folk"])
