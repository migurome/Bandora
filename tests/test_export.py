import unittest

from weave.db import connect
from weave.export import build
from weave.store import Store

HASH = "16925ed8f96eb621ecd56c2c8ba3da6e"


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.s = Store(connect(":memory:"))
        self.ext = self.s.upsert_deezer(4163, "Extremoduro", 900)
        self.pla = self.s.upsert_deezer(4164, "Platero y Tú", 300)
        self.fuga = self.s.upsert_deezer(4165, "La Fuga", 200)
        self.s.set_details(self.ext, picture=f"https://cdn-images.dzcdn.net/images/artist/{HASH}/250x250-000000-80-0-0.jpg")
        self.s.set_genres(self.ext, [("rock", 5)], "lastfm")
        self.s.add_relations([(self.ext, self.pla)], "member", "wikidata")
        self.s.set_related(self.ext, [self.fuga], "deezer")

    def row(self, out, aid):
        return next(a for a in out["artists"] if a[0] == aid)

    def test_export_shape(self):
        out = build(self.s)
        self.assertIn([self.pla, 2], out["related"][str(self.ext)])
        self.assertIn(self.fuga, out["related"][str(self.ext)])  # parecido: solo el id
        ext = self.row(out, self.ext)
        self.assertEqual(ext[1:5], ["Extremoduro", 900, HASH, 4163])
        self.assertEqual(out["families"][ext[5]]["name"], "Rock")
        self.assertEqual(ext[6], "rock")
        self.assertTrue(out["version"] and out["rockFirst"])
        self.assertEqual(self.row(out, self.pla)[3], "")  # sin foto

    def test_related_order_matches_store(self):
        out = build(self.s)
        expected = [[r["id"], k] if (k := ["similar", "influence", "member"].index(r["kind"])) else r["id"] for r in self.s.artist(self.ext)["related"]]
        self.assertEqual(out["related"][str(self.ext)], expected)



class ExportLimitTest(unittest.TestCase):
    def test_related_capped(self):
        s = Store(connect(":memory:"))
        a = s.upsert_deezer(1, "A")
        s.set_related(a, [s.upsert_deezer(100 + i, f"B{i}") for i in range(40)], "deezer")
        self.assertEqual(len(build(s)["related"][str(a)]), 25)

    def test_unreachable_stubs_are_left_out(self):
        s = Store(connect(":memory:"))
        a = s.upsert_deezer(1, "A")
        s.set_related(a, [s.upsert_deezer(100 + i, f"B{i}") for i in range(40)], "deezer")
        ids = {row[0] for row in build(s)["artists"]}
        self.assertEqual(len(ids), 26)  # A y sus 25 primeras; las de más allá no se pueden alcanzar desplegando
if __name__ == "__main__":
    unittest.main()
