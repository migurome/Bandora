// Datos de Weave bands en el navegador, sin servidor: data/weave.json (python -m weave.export) para buscar,
// abrir fichas, desplegar y trazar caminos sin conexión; las canciones se piden a Deezer en vivo (JSONP: su API no
// deja llamarla con fetch desde otra web) y nunca se guardan, porque sus URLs caducan.
const Data = (() => {
  const KINDS = ['similar', 'influence', 'member'];
  const nrm = s => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '');
  const byId = new Map(), list = [];
  let families = [], related = {}, adj = null;
  const ready = fetch('data/weave.json').then(r => { if (!r.ok) throw new Error('datos ' + r.status); return r.json(); }).then(d => {
    families = d.families; related = d.related;
    for (const [id, name, fans, pic, dz, fam, genre] of d.artists) {
      const a = { id, name, fans, pic, dz, fam, genre, k: nrm(name) };
      byId.set(id, a); list.push(a);
    }
  });
  const picture = p => !p ? null : /^[0-9a-f]{32}$/.test(p) ? `https://cdn-images.dzcdn.net/images/artist/${p}/250x250-000000-80-0-0.jpg` : p;
  const rel = id => (related[id] || []).map(x => Array.isArray(x) ? x : [x, 0]);

  // Búsqueda: por el principio del nombre normalizado; primero los que se pueden desplegar, luego los más seguidos
  async function search(q, limit = 6) {
    await ready;
    const k = nrm(q);
    if (!k) return [];
    return list.filter(a => a.k.startsWith(k))
      .sort((a, b) => (b.id in related) - (a.id in related) || b.fans - a.fans).slice(0, limit)
      .map(a => ({ id: a.id, name: a.name, fans: a.fans, picture: picture(a.pic) }));
  }
  // Ficha completa con la misma forma que daba /api/artist
  async function artist(id) {
    await ready;
    const a = byId.get(id);
    if (!a) throw new Error('artista desconocido');
    const f = families[a.fam];
    return { id, name: a.name, fans: a.fans, picture: picture(a.pic), family: f.name, color: f.color, familyOrder: a.fam,
             genres: [a.genre], related: rel(id).filter(([r]) => byId.has(r))
               .map(([r, k]) => ({ id: r, name: byId.get(r).name, fans: byId.get(r).fans, kind: KINDS[k] })) };
  }
  // Camino más corto sin red (BFS sobre las relaciones como aristas no dirigidas, como weave/graph.py)
  async function path(from, to) {
    await ready;
    if (!adj) {
      adj = new Map();
      const link = (x, y) => { if (!adj.has(x)) adj.set(x, []); adj.get(x).push(y); };
      for (const id in related) for (const [r] of rel(id)) { link(+id, r); link(r, +id); }
    }
    if (!byId.has(from) || !byId.has(to)) return null;
    const prev = new Map([[from, null]]), queue = [from];
    for (let i = 0; i < queue.length && !prev.has(to); i++) {
      for (const n of adj.get(queue[i]) || []) if (!prev.has(n)) { prev.set(n, queue[i]); queue.push(n); }
    }
    if (!prev.has(to)) return null;
    const out = [];
    for (let n = to; n != null; n = prev.get(n)) out.unshift({ id: n, name: byId.get(n).name });
    return out;
  }
  // Deezer en vivo por JSONP
  let seq = 0;
  function deezer(route) {
    return new Promise((resolve, reject) => {
      const cb = '__dz' + ++seq, s = document.createElement('script');
      const done = () => { clearTimeout(timer); delete window[cb]; s.remove(); };
      const timer = setTimeout(() => { done(); reject(new Error('Deezer no responde')); }, 8000);
      window[cb] = d => { done(); d && d.error ? reject(new Error(d.error.message || 'Deezer')) : resolve(d); };
      s.onerror = () => { done(); reject(new Error('sin conexión')); };
      s.src = `https://api.deezer.com${route}${route.includes('?') ? '&' : '?'}output=jsonp&callback=${cb}`;
      document.head.appendChild(s);
    });
  }
  async function tracks(id) {
    await ready;
    const a = byId.get(id);
    if (!a || !a.dz) return [];
    const d = await deezer(`/artist/${a.dz}/top?limit=10`);
    return (d.data || []).filter(t => t.preview).map(t => ({ title: t.title, preview: t.preview }));
  }
  return { ready, search, artist, path, tracks, deezer, norm: nrm };
})();
