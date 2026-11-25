import unittest

from weave.db import connect
from weave.store import Store


def count(s, table):
    return s.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.s = Store(connect(":memory:"))

    def test_same_mbid_merges_two_deezer_ids(self):
        a = self.s.upsert_deezer(3614, "B.B. King", 1707660)
        b = self.s.upsert_deezer(54984, "B.B.King", 22864)
        self.assertEqual(self.s.attach_mbid(a, "mb-bbking"), a)
        keep = self.s.attach_mbid(b, "mb-bbking")
        self.assertEqual(keep, a)
        self.assertEqual(count(self.s, "artist"), 1)
        self.assertEqual(self.s.by_source("deezer", 54984), a)
        self.assertEqual(self.s.by_source("deezer", 3614), a)

    def test_same_name_without_mbid_merges(self):
        a = self.s.upsert_deezer(3614, "B.B. King", 1707660)
        b = self.s.upsert_deezer(54984, "B.B.King", 22864)
        self.assertEqual(self.s.dedupe_by_name(b), a)
        self.assertEqual(count(self.s, "artist"), 1)

    def test_homonyms_with_different_mbid_stay_apart(self):
        a = self.s.upsert_deezer(9148, "Marea")
        b = self.s.upsert_deezer(777, "Marea")
        self.s.attach_mbid(a, "mb-marea-es")
        self.s.attach_mbid(b, "mb-marea-otra")
        self.assertEqual(self.s.dedupe_by_name(b), b)
        self.assertEqual(count(self.s, "artist"), 2)

    def test_merge_moves_everything_and_drops_self_relations(self):
        keep = self.s.upsert_deezer(1, "Keep", 10)
        drop = self.s.upsert_deezer(2, "Drop", 5)
        x = self.s.upsert_deezer(3, "X")
        y = self.s.upsert_deezer(4, "Y")
        self.s.set_related(x, [drop])
        self.s.set_related(drop, [x, y, keep])
        self.s.set_related(keep, [y, drop])
        self.s.set_genres(drop, [("rock", 2)], "musicbrainz")
        self.s.set_level(drop, 2)
        self.assertEqual(self.s.merge(keep, drop), keep)
        rel = self.s.conn.execute("SELECT a, b FROM relation").fetchall()
        pairs = [(r[0], r[1]) for r in rel]
        self.assertEqual(pairs.count((keep, y)), 1)
        self.assertTrue(all(a != b for a, b in pairs))
        self.assertIn((x, keep), pairs)
        self.assertIn((keep, x), pairs)
        self.assertIsNone(self.s.artist(drop))
        k = self.s.artist(keep)
        self.assertEqual((k["level"], k["fans"], k["genres"]), (2, 10, ["rock"]))
        aliases = {r[0] for r in self.s.conn.execute("SELECT name FROM alias WHERE artist_id=?", (keep,))}
        self.assertEqual(aliases, {"Keep", "Drop"})
        self.assertEqual(self.s.by_source("deezer", 2), keep)

    def test_merge_keeps_name_of_most_popular(self):
        keep = self.s.upsert_deezer(54984, "B.B.King", 10)
        drop = self.s.upsert_deezer(3614, "B.B. King", 1707660)
        self.s.merge(keep, drop)
        k = self.s.artist(keep)
        self.assertEqual((k["name"], k["fans"]), ("B.B. King", 1707660))
