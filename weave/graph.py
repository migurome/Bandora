"""Grafo de artistas sin red: relacionadas y caminos más cortos sobre la tabla relation."""
from collections import defaultdict


def related_ids(store, artist_id: int) -> list[int]:
    return [b for _, b in store.edges(artist_id)]


def find_path(store, a: int, b: int, max_nodes: int = 200_000) -> list[int] | None:
    """Camino más corto entre a y b. Las relaciones se tratan como no dirigidas: si Deezer dice que A se parece
    a B, desde B también se llega a A (así se alcanzan artistas sin relacionadas propias)."""
    if a == b:
        return [a]
    adj = defaultdict(set)
    for x, y in store.edges():
        adj[x].add(y)
        adj[y].add(x)
    parents = ({a: None}, {b: None})
    frontier = ([a], [b])
    while frontier[0] and frontier[1] and len(parents[0]) + len(parents[1]) < max_nodes:
        side = 0 if len(frontier[0]) <= len(frontier[1]) else 1  # se expande el frente más pequeño
        mine, other = parents[side], parents[1 - side]
        nxt = []
        for x in frontier[side]:
            for y in sorted(adj[x]):  # orden fijo: mismo resultado en cada llamada
                if y in mine:
                    continue
                mine[y] = x
                if y in other:
                    return _join(parents, y)
                nxt.append(y)
        frontier = (nxt, frontier[1]) if side == 0 else (frontier[0], nxt)
    return None


def _join(parents, meet):
    left, n = [], meet
    while n is not None:
        left.append(n)
        n = parents[0][n]
    right, n = [], parents[1][meet]
    while n is not None:
        right.append(n)
        n = parents[1][n]
    return left[::-1] + right
