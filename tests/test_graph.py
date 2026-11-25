import unittest

from weave.db import connect
from weave.graph import find_path, related_ids
from weave.store import Store


def build(edges, isolated=()):
    """Crea un artista por número y las relaciones dadas; devuelve (store, {número: id interno})."""
    s = Store(connect(":memory:"))
    nums = sorted({n for a, bs in edges.items() for n in [a, *bs]} | set(isolated))
    ids = {n: s.upsert_deezer(n, f"Banda {n}") for n in nums}
    for a, bs in edges.items():
        s.set_related(ids[a], [ids[b] for b in bs])
    return s, ids


class GraphTest(unittest.TestCase):
    def test_related_ids_in_rank_order(self):
        s, ids = build({1: [3, 2]})
        self.assertEqual(related_ids(s, ids[1]), [ids[3], ids[2]])

    def test_path_uses_reverse_edges(self):
        s, ids = build({1: [2], 2: [4], 4: [6], 6: [7], 8: [7]})  # 8 solo enlaza hacia 7
        self.assertEqual(find_path(s, ids[1], ids[8]), [ids[n] for n in [1, 2, 4, 6, 7, 8]])

    def test_path_to_artist_without_related(self):
        s, ids = build({1: [2], 2: [4], 4: [6], 6: [9]})  # 9 no tiene relacionadas propias
        self.assertEqual(find_path(s, ids[1], ids[9]), [ids[n] for n in [1, 2, 4, 6, 9]])

    def test_path_same_and_disconnected(self):
        s, ids = build({1: [2]}, isolated=[5])
        self.assertEqual(find_path(s, ids[1], ids[1]), [ids[1]])
        self.assertIsNone(find_path(s, ids[1], ids[5]))

    def test_path_is_shortest_when_first_meeting_is_longer(self):
        # Desde 1, el primer vecino (2) toca un nodo que el otro lado alcanzó a distancia 2;
        # el segundo vecino (3) toca uno a distancia 1. El camino bueno es 1-3-5-9 (3 saltos), no 1-2-6-7-9.
        s, ids = build({1: [2, 3], 2: [6], 6: [7], 7: [9], 3: [5], 5: [9], 9: [8], 8: [6]})
        self.assertEqual(len(find_path(s, ids[1], ids[9])), 4)

    def test_path_is_shortest(self):
        s, ids = build({1: [2, 10], 2: [3], 3: [4], 4: [5], 5: [6], 10: [11], 11: [6]})
        self.assertEqual(find_path(s, ids[1], ids[6]), [ids[n] for n in [1, 10, 11, 6]])
