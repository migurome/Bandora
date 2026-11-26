// Datos de Weave bands en el navegador, sin servidor: data/weave.json (python -m weave.export) para buscar,
// abrir fichas, desplegar y trazar caminos sin conexión. Con red, Deezer en vivo (JSONP: su API no deja llamarla
// con fetch desde otra web) para las canciones (sus URLs caducan: nunca se guardan), los artistas que no están en
// los datos (id «dz<id de Deezer>») y las relacionadas de quien no las tiene guardadas.
const Data = (() => {
  const KINDS = ['similar', 'influence', 'member'];
  const nrm = s => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '');
  const byId = new Map(), list = [], byDz = new Map(), live = new Map();  // live: artistas de Deezer vistos en vivo
  let families = [], related = {}, adj = null, rockFirst = null, version = '';
  const ready = fetch('data/weave.json').then(r => { if (!r.ok) throw new Error('datos ' + r.status); return r.json(); }).then(d => {
    families = d.families; related = d.related; version = d.version; rockFirst = new RegExp(d.rockFirst);
    families.forEach(f => { f.rx = f.pattern ? new RegExp(f.pattern) : null; });
    for (const [id, name, fans, pic, dz, fam, genre] of d.artists) {
      const a = { id, name, fans, pic, dz, fam, genre, k: nrm(name) };
      byId.set(id, a); list.push(a); if (dz) byDz.set(dz, id);
    }
  });
  // foto: hash de Deezer o URL; la imagen genérica de Deezer (sin hash) cuenta como «sin foto»
  const BLANK = /\/artist\/\/|d41d8cd98f00b204e9800998ecf8427e/;
  const picture = p => !p || BLANK.test(p) ? null : /^[0-9a-f]{32}$/.test(p) ? `https://cdn-images.dzcdn.net/images/artist/${p}/250x250-000000-80-0-0.jpg` : p;
  const rel = id => (related[id] || []).map(x => Array.isArray(x) ? x : [x, 0]);

  // Búsqueda: por el principio del nombre normalizado; primero los que se pueden desplegar, luego los más seguidos
  async function search(q, limit = 6) {
    await ready;
    const k = nrm(q);
    if (!k) return [];
    const out = list.filter(a => a.k.startsWith(k))
      .sort((a, b) => (b.id in related) - (a.id in related) || b.fans - a.fans).slice(0, limit)
      .map(a => ({ id: a.id, name: a.name, fans: a.fans, picture: picture(a.pic) }));
    if (out.length >= limit) return out;
    const more = await deezer('/search/artist?limit=' + limit + '&q=' + encodeURIComponent(q)).then(d => d.data || [], () => []);
    for (const x of more) {  // lo de Deezer que no está ya: con su id de los datos si lo tenemos, si no «dz…»
      const r = byDz.has(x.id) ? byId.get(byDz.get(x.id)) : null;
      const hit = r ? { id: r.id, name: r.name, fans: r.fans, picture: picture(r.pic) } : remember(x);
      if (out.length < limit && !out.some(o => o.id === hit.id || nrm(o.name) === nrm(hit.name))) out.push(hit);
    }
    return out;
  }
  function remember(x) {  // artista de Deezer en vivo: lo básico para mostrarlo; la ficha completa en artist()
    const id = 'dz' + x.id;
    if (!live.has(id)) live.set(id, { id, dz: x.id, name: x.name, fans: x.nb_fan || 0, picture: x.picture_medium || null });
    const a = live.get(id);
    return { id, name: a.name, fans: a.fans, picture: a.picture };
  }
  // Familia por los géneros, con las mismas reglas que weave/families.py (la primera reconocible manda)
  function familyOf(genres) {
    for (const g of genres) {
      if (rockFirst.test(g)) return families.findIndex(f => f.name === 'Rock');
      const i = families.findIndex(f => f.rx && f.rx.test(g));
      if (i >= 0) return i;
    }
    return families.length - 1;
  }
  async function liveArtist(id) {
    let a = live.get(id);
    if (!a) {
      const x = await deezer('/artist/' + id.slice(2));
      remember(x); a = live.get(id);
    }
    if (!a.genres) {  // géneros del primer disco, como el respaldo del servidor
      const albums = await deezer(`/artist/${a.dz}/albums?limit=1`).then(d => d.data || []);
      const album = albums[0] && await deezer('/album/' + albums[0].id);
      a.genres = ((album && album.genres && album.genres.data) || []).slice(0, 2).map(g => g.name.toLowerCase());
    }
    const fam = familyOf(a.genres), f = families[fam];
    return { id, name: a.name, fans: a.fans, picture: a.picture, family: f.name, color: f.color, familyOrder: fam,
             genres: a.genres.length ? a.genres : ['sin género'], related: [] };
  }
  // Relacionadas en vivo para quien no las tiene guardadas (artistas de Deezer o de los datos solo con nombre)
  async function more(id) {
    await ready;
    const dz = typeof id === 'string' ? +id.slice(2) : (byId.get(id) || {}).dz;
    if (!dz) return [];
    const d = await deezer(`/artist/${dz}/related?limit=20`);
    return (d.data || []).map(x => {
      const r = byDz.has(x.id) ? byId.get(byDz.get(x.id)) : null;
      const b = r ? { id: r.id, name: r.name, fans: r.fans } : remember(x);
      return { id: b.id, name: b.name, fans: b.fans, kind: 'similar' };
    });
  }
  // Ficha completa con la misma forma que daba /api/artist
  async function artist(id) {
    await ready;
    if (typeof id === 'string') return liveArtist(id);
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
    if (api.offline) return Promise.reject(new Error('sin conexión'));
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
  // Lo que falte en los datos (foto; familia de quien no tiene géneros), pedido a Deezer una vez y recordado en el
  // móvil (localStorage): { picture, family, color, order, genre }
  const EXTRA = 'weave-extra', known = JSON.parse(localStorage.getItem(EXTRA) || '{}');
  async function extra(id) {
    await ready;
    if (id in known) return known[id];
    const a = typeof id === 'string' ? live.get(id) : byId.get(id);
    const dz = typeof id === 'string' ? id.slice(2) : a && a.dz;
    if (!a || !dz) return null;
    const out = { picture: a.picture || picture(a.pic) };
    if (!out.picture) out.picture = picture((await deezer('/artist/' + dz)).picture_medium || '');
    if (typeof id !== 'string' && a.fam === families.length - 1) {  // «Otros»: géneros del primer disco
      const albums = await deezer(`/artist/${dz}/albums?limit=1`).then(d => d.data || []);
      const album = albums[0] && await deezer('/album/' + albums[0].id);
      const genres = ((album && album.genres && album.genres.data) || []).slice(0, 2).map(g => g.name.toLowerCase());
      const fam = familyOf(genres);
      if (fam !== families.length - 1) Object.assign(out, { family: families[fam].name, color: families[fam].color, order: fam, genre: genres[0] });
    }
    known[id] = out;
    try { localStorage.setItem(EXTRA, JSON.stringify(known)); } catch { /* lleno: solo en memoria */ }
    return out;
  }
  const photo = id => extra(id).then(x => x && x.picture);
  async function tracks(id) {
    await ready;
    const dz = typeof id === 'string' ? id.slice(2) : (byId.get(id) || {}).dz;
    if (!dz) return [];
    const d = await deezer(`/artist/${dz}/top?limit=10`);
    return (d.data || []).filter(t => t.preview).map(t => ({ title: t.title, preview: t.preview }));
  }
  const info = () => ready.then(() => ({ version, artists: list.length }));  // para /version
  const api = { ready, info, search, artist, more, path, tracks, photo, extra, deezer, norm: nrm, offline: false };  // offline: simula sin red
  return api;
})();
