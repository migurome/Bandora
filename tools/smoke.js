// Prueba de humo de Weave: se inyecta al final de la página (sustituye a la última llamada render();)
render();
window.onerror = (m, src, line) => { document.title = 'ERR ' + m + ' @' + line; };
window.addEventListener('unhandledrejection', e => { document.title = 'ERR(promesa) ' + (e.reason && e.reason.message); });
const clk = el => el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
const nodeG = name => [...document.querySelectorAll('g.node')].find(g => d3.select(g).datum().name === name);
const opt = k => [...document.querySelectorAll('g.opt')].find(g => d3.select(g).datum().key === k);
const cmd = v => { $('q').value = v; $('q').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' })); };
const typeIn = v => { $('q').value = v; $('q').dispatchEvent(new Event('input')); };
setTimeout(async () => {
  const r = [];
  const ok = (name, cond) => r.push((cond ? 'ok ' : 'MAL ') + name);
  try {
    await sleep(600);
    ok('fondo animado al arrancar', $('ambient').classList.contains('on'));
    typeIn('Marea'); await sleep(2500);
    ok('el fondo se va al buscar', !$('ambient').classList.contains('on'));
    ok('busqueda', $('results').querySelectorAll('li').length > 0);
    $('results').querySelector('li').click(); await sleep(2500);
    ok('origen añadido', nodes.length === 1 && nodes[0].name === 'Marea' && nodes[0].selected);
    const hero = nodes[0], [hx, hy] = d3.zoomTransform(document.getElementById('svg')).apply([hero.x, hero.y]);
    ok('buscado grande y centrado', hero.hero && radius(hero) >= 50 && Math.abs(hx - innerWidth / 2) < 40);
    ok('color de familia', d3.select(nodeG('Marea')).select('.dot').attr('fill') === '#a3c9f5');
    ok('familia del servidor', nodes[0].genre === 'Rock' && nodes[0].color === '#a3c9f5');
    clk(nodeG('Marea')); await sleep(300);
    ok('menu 6 opciones', document.querySelectorAll('g.opt').length === 6);
    clk(opt('expand')); await sleep(6000);
    ok('desplegar', nodes.length === 6 && opt('expand').classList.contains('off'));
    ok('al desplegar vuelve a normal', !hero.hero && hero.fx == null);
    const svgSel = d3.select('#svg');
    svgSel.call(zoom.transform, d3.zoomIdentity.scale(0.5)); await sleep(100);
    const far = root.classed('far');
    svgSel.call(zoom.transform, d3.zoomIdentity); await sleep(100);
    ok('zoom: nombres por umbral', far && !root.classed('far'));
    const tipOn = t => { nodeG('Marea').dispatchEvent(new PointerEvent('pointermove', { bubbles: true, pointerType: t, clientX: 50, clientY: 50 })); return $('tip').style.display === 'block'; };
    $('tip').style.display = 'none'; const touchTip = tipOn('touch'); const mouseTip = tipOn('mouse'); $('tip').style.display = 'none';
    ok('etiqueta solo con ratón', !touchTip && mouseTip);
    ok('spotify abre la app en android', spotifyUrl('Marea', 'Mozilla/5.0 (Linux; Android 12)') .startsWith('intent:search:Marea#Intent;scheme=spotify;package=com.spotify.music;S.browser_fallback_url=https%3A%2F%2Fopen.spotify.com%2Fsearch%2FMarea')
       && spotifyUrl('Marea', 'Mozilla/5.0 (Windows NT 10.0)') === 'https://open.spotify.com/search/Marea');
    { const w = working(sleep(700)); await sleep(500); ok('una espera corta no saca el juego', !game.playing()); await w; await sleep(100); }
    const wait = working(sleep(2500)); await sleep(1500);
    const bar = document.querySelector('.ui .bar'), word = bar.querySelector('.searching');
    ok('espera: «searching» en la barra y un juego', bar.classList.contains('busy') && word && word.textContent === 'searching' && game.playing());
    await wait; await sleep(700);
    cmd('/debug pong'); await sleep(600);
    $('game').dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: 150, clientY: 400 }));
    ok('pong: la pala sigue el dedo', game.mode() === 'pong' && game.paddle() === 150);
    const st = game.state(), c = st.circles[3];  // un botón del menú: se lanza la bola contra él
    Object.assign(st.ball, { x: c.x, y: c.y + c.r + 40, vx: 0, vy: -5 }); await sleep(800);
    ok('pong: la bola enciende el botón que golpea', st.circles.length === 7 && game.state().lit[3]);
    cmd('/debug bobbl'); await sleep(600);  // basta el principio
    const b0 = game.bubbles();
    const shoot = (x, y) => ['pointerdown', 'pointermove', 'pointerup'].forEach(t => $('game').dispatchEvent(new PointerEvent(t, { bubbles: true, clientX: x, clientY: y })));
    shoot(innerWidth / 2 + 30, 200); await sleep(1500);
    const b1 = game.bubbles();
    ok('burbujas: panal con iconos y disparo que se queda', game.mode() === 'bobble' && b0.count > 10 && b1.shots === 1 && !b1.flying && b1.count !== b0.count);
    cmd('/debug off'); await sleep(700);
    ok('/debug off lo para', !game.playing());
    ok('al parar libera el lienzo del juego', $('game').width === 0);
    cmd('/debug pong'); await sleep(600);
    { const n0 = nodes.length; $('clear').click(); await sleep(700);
      ok('✕ sale del debug sin borrar el mapa', !game.playing() && nodes.length === n0 && n0 > 0); }
    cmd('/debug id'); await sleep(300);
    { const ids = [...document.querySelectorAll('g.node text.dbgid')].map(t => t.textContent);
      ok('/debug id: cada bola enseña su id único', !game.playing() && ids.length === nodes.length && ids.every((t, i) => t === '#' + d3.select(document.querySelectorAll('g.node')[i]).datum().id)); }
    cmd('/debug off'); await sleep(300);
    ok('/debug off oculta los ids', [...document.querySelectorAll('g.node text.dbgid')].every(t => !t.textContent));
    ok('fin de espera: sin «searching» ni juego', !bar.classList.contains('busy') && !game.playing());
    ok('motivo en la línea', links.length > 0 && links.every(l => ['similar', 'member', 'influence'].includes(l.kind)));
    clk(opt('play')); await sleep(2000);
    ok('play', !player.paused && document.querySelector('.node.playing'));
    clk(opt('play')); await sleep(300);
    ok('pausa', player.paused);
    clk(opt('next')); await sleep(2000);
    ok('siguiente', !player.paused && queue.i === 1);
    $('play').click(); await sleep(300);
    ok('pausa pie', player.paused);
    cmd('/label on'); ok('label on', getComputedStyle($('legend')).display !== 'none');
    clk($('legend').querySelector('button')); ok('filtro', document.querySelectorAll('.node.off').length > 0);
    clk($('legend').querySelector('button'));
    cmd('/label off'); ok('label off', getComputedStyle($('legend')).display === 'none');
    const sink = nodes.find(n => n.name !== 'Marea');
    select(sink); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' })); await sleep(300);
    ok('supr', nodes.length === 5);
    const other = nodes.find(n => n.name !== 'Marea' && n !== sink);
    queue = { id: other.id, list: [], i: 0 };  // como si sonara
    select(other); clk(nodeG(other.name)); await sleep(300); clk(opt('remove')); await sleep(300);
    ok('quitar desde el menú', nodes.length === 4 && !byId.has(other.id));
    ok('quitar el que suena lo calla', queue.id == null);
    clk(document.getElementById('svg')); await sleep(200);
    ok('fondo cierra', !document.querySelector('g.opt') && selId == null);
    // arrastrar desde el botón de desplegar de Marea hasta Michael Jackson teje el camino dentro del mapa
    await addOrigin(await findArtist('Michael Jackson')); await sleep(800);
    const before = nodes.length, marea = nodes.find(n => n.name === 'Marea'), mj = nodes.find(n => n.name === 'Michael Jackson');
    wantFit = autoFit = false; sim.stop(); d3.select('#svg').interrupt();  // mapa quieto: las coordenadas no se mueven
    closeAll(); clk(nodeG('Marea')); await sleep(400);
    const at = el => { const r = el.getBoundingClientRect(); return { clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, bubbles: true, view: window }; };
    const from = at(opt('expand').querySelector('.bg')), to = at(nodeG('Michael Jackson').querySelector('.dot'));
    // con el dedo (eventos táctiles): se prueba sin tejer el camino, solo que encuentra el destino
    const realConnect = connectPath; let hit = null; connectPath = (a, b) => { hit = [a.name, b.name]; };
    const tch = p => [new Touch({ identifier: 7, target: opt('expand'), clientX: p.clientX, clientY: p.clientY })];
    const tev = (type, p) => opt('expand').dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true,
      touches: type === 'touchend' ? [] : tch(p), targetTouches: type === 'touchend' ? [] : tch(p), changedTouches: tch(p) }));
    tev('touchstart', from); tev('touchmove', { clientX: from.clientX + 20, clientY: from.clientY }); tev('touchmove', to);
    const wire = gWire.select('line'), wireOk = !wire.empty() && isFinite(+wire.attr('x2'));
    tev('touchend', to); connectPath = realConnect;
    ok('conectar con el dedo' + (hit ? '' : ' ' + JSON.stringify({ wireOk, names: nodes.map(n => n.name), mj: !!mj })), wireOk && hit && hit[0] === 'Marea' && hit[1] === 'Michael Jackson');
    closeAll(); clk(nodeG('Marea')); await sleep(900);  // tras un toque, d3 ignora el ratón 500 ms
    opt('expand').dispatchEvent(new MouseEvent('mousedown', { ...from, button: 0 }));
    window.dispatchEvent(new MouseEvent('mousemove', { ...from, clientX: from.clientX + 20 }));
    window.dispatchEvent(new MouseEvent('mousemove', to));
    window.dispatchEvent(new MouseEvent('mouseup', to));
    await sleep(15000);
    ok('conectar arrastrando', nodes.length > before && links.some(l => l.path) && nodes.includes(marea) && nodes.includes(mj));
    // arrastrar un círculo lo mueve y no conecta
    const g0 = nodeG('Michael Jackson'), x0 = mj.x, nLinks = links.length, p0 = at(g0.querySelector('.dot'));
    g0.querySelector('.dot').dispatchEvent(new MouseEvent('mousedown', { ...p0, button: 0 }));
    window.dispatchEvent(new MouseEvent('mousemove', { ...p0, clientX: p0.clientX + 60 }));
    window.dispatchEvent(new MouseEvent('mouseup', { ...p0, clientX: p0.clientX + 60 })); await sleep(200);
    ok('arrastrar mueve el círculo', mj.x > x0 + 20 && links.length === nLinks);
    cmd('/help'); await sleep(200);
    { const items = [...$('results').querySelectorAll('li')];
      ok('/help lista los comandos y enlaza la ayuda', items.some(li => li.textContent.startsWith('/undo')) && !!$('results').querySelector('a[href="ayuda.html"]')); }
    $('results').innerHTML = '';
    ok('norm: «y», «&» y «and» valen igual', norm('Fito y Fitipaldis') === norm('Fito & Fitipaldis') && Data.norm('Fito and Fitipaldis') === norm('Fito & Fitipaldis') && norm('Y') === 'y');
    { const f = (await Data.search('Fito')).filter(r => /fitipaldis/i.test(r.name)); ok('un solo Fito y Fitipaldis' + (f.length === 1 ? '' : ' ' + f.map(r => r.name + '#' + r.id).join(',')), f.length === 1); }
    typeIn('/'); await sleep(200);
    ok('/debug no sale en la lista de comandos', ![...$('results').querySelectorAll('li')].some(li => li.textContent.startsWith('/debug')));
    cmd('/version'); await sleep(400);
    ok('/version: versión de la app y de los datos', $('results').textContent.includes('Weave bands ' + VERSION) && /\d+\.\d{3} artistas/.test($('results').textContent));
    cmd('/version log'); await sleep(300);
    { const li = [...$('results').querySelectorAll('li')];
      ok('/version log: cambios por versión, el último arriba', li.length > 5 && li[0].textContent.startsWith(VERSION) && /0\.1/.test(li.at(-1).textContent)); }
    $('results').innerHTML = '';
    { const [r] = await Data.search('Extremoduro'); cmd('/debug id ' + r.id); await sleep(800);
      ok('/debug id <número> saca ese artista al mapa', nodes.some(n => n.id === r.id) && !$('q').classList.contains('err'));
      cmd('/debug id 999999999'); await sleep(800); ok('/debug id con un id que no existe: error', $('q').classList.contains('err')); }
    cmd('/debug off'); await sleep(300);
    cmd('/form x'); await sleep(200); ok('comando erróneo', $('q').classList.contains('err'));
    cmd('/from Marea to Michael Jackson'); await sleep(25000);
    ok('camino', nodes.length >= 3 && links.every(l => l.path));  // la longitud depende de los datos
    // corona: el primer ✕ deja solo las favoritas; el segundo borra todo
    const fav = nodes.find(n => n.name === 'Marea'); closeAll(); clk(nodeG('Marea')); await sleep(300); clk(opt('pin')); await sleep(200);
    ok('corona marca', fav.pinned && getComputedStyle(nodeG('Marea').querySelector('.pinmark')).display !== 'none');
    { const g = nodeG('Marea'), c = g.querySelector('.dot').getBoundingClientRect(), k = g.querySelector('.pinmark').getBoundingClientRect(),
        r = radius(d3.select(g).datum()) * d3.zoomTransform($('svg')).k, top = c.top + c.height / 2 - r;  // el radio de la bola, no el del dibujo (su transición se congela aquí)
      ok('corona a medida del círculo ' + JSON.stringify([r, k.width, k.bottom - top].map(Math.round)), k.width > r * 0.75 && k.width < r * 1.05 && k.bottom > top + r * 0.05 && k.bottom < top + r * 0.3); }
    $('clear').click(); await sleep(300);
    ok('✕ deja las favoritas', nodes.length === 1 && nodes[0] === fav);
    $('clear').click(); await sleep(300);
    ok('segundo ✕ borra todo', nodes.length === 0);
    cmd('/undo'); await sleep(300);
    ok('/undo deshace el ✕', nodes.length === 1 && nodes[0].name === 'Marea' && nodes[0].pinned);
    cmd('/undo'); await sleep(300);
    const before2 = nodes.length;
    ok('/undo otra vez recupera el camino', before2 >= 3 && links.some(l => l.path));
    localStorage.removeItem('weave-maps');
    cmd('/save Prueba humo'); await sleep(200);
    $('clear').click(); $('clear').click(); await sleep(300);
    typeIn('/load Pru'); await sleep(200);
    ok('/load sugiere los mapas guardados', [...$('results').querySelectorAll('li')].some(li => li.textContent === 'Prueba humo'));
    cmd('/load prueba humo'); await sleep(500);
    ok('/load recupera el mapa (sin red)', nodes.length === before2 && links.some(l => l.path) && nodes.every(n => isFinite(n.x)));
    cmd('/load no existe'); await sleep(200); ok('/load de un mapa que no existe avisa', $('q').classList.contains('err'));
    $('clear').click(); $('clear').click(); await sleep(300);
    $('q').value = 'Extremoduro'; $('q').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' })); await sleep(4000);
    ok('intro inmediato añade el primero', nodes.length === 1 && nodes[0].name === 'Extremoduro');
    $('clear').click(); await sleep(300);
    ok('clear', nodes.length === 0 && player.paused && !player.getAttribute('src'));
    // Deezer en vivo: un artista que no viene de los datos entra con ficha completa y se puede desplegar
    const live = await Data.artist('dz27').catch(e => null);  // 27 = Daft Punk en Deezer
    const liveRel = await Data.more('dz27').catch(e => []);
    ok('en vivo: ficha con familia y relacionadas', live && live.name === 'Daft Punk' && live.family === 'Electrónica' && liveRel.length > 0);
    const mtr = await Data.tracks(nodes.length ? nodes[0].id : (await Data.search('Marea'))[0].id).catch(() => []);
    ok('en vivo: canciones con preview', mtr.length > 0 && mtr.every(t => t.preview));
    Data.offline = true;
    const offSearch = await Data.search('Marea'), offMore = await Data.more('dz27').then(() => 'ok', () => 'falla');
    Data.offline = false;
    ok('sin red: busca en lo guardado y lo de Deezer falla sin colgarse', offSearch.length > 0 && offMore === 'falla');
    // sin foto: el nombre dentro de la bola (y no debajo); las fotos que faltan se piden a Deezer
    const bare = addArtist({ id: 'prueba-sin-foto', name: 'Kanka de Prueba', fans: 1, genres: ['x'], family: 'Otros', color: '#c0c6cf', familyOrder: 9, picture: null });
    bare.picture = null; render(); await sleep(200);
    const bg = nodeG('Kanka de Prueba');
    ok('sin foto: nombre dentro de la bola', bg && bg.querySelectorAll('text.inner tspan').length > 0 && !bg.querySelector('text.label tspan'));
    removeNode(bare); await sleep(200);
    const ph = await Data.photo((await Data.search('Kanka'))[0].id).catch(() => 'falla');
    ok('foto en vivo de quien no la tiene guardada', ph === null || /^https:/.test(ph));
    { const apis = performance.getEntriesByType('resource').map(e => e.name).filter(n => n.startsWith(location.origin + '/api/')); ok('sin /api (datos exportados)' + (apis.length ? ' ' + apis.slice(0, 3).join(' ') : ''), !apis.length); }
  } catch (e) { r.push('EXCEPCION ' + e.message); }
  document.title = r.join(' | ');
}, 500);
