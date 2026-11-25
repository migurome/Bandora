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
    typeIn('Marea'); await sleep(2500);
    ok('busqueda', $('results').querySelectorAll('li').length > 0);
    $('results').querySelector('li').click(); await sleep(2500);
    ok('origen añadido', nodes.length === 1 && nodes[0].name === 'Marea' && nodes[0].selected);
    ok('color de familia', d3.select(nodeG('Marea')).select('.dot').attr('fill') === '#a3c9f5');
    ok('familia del servidor', nodes[0].genre === 'Rock' && nodes[0].color === '#a3c9f5');
    clk(nodeG('Marea')); await sleep(300);
    ok('menu 5 opciones', document.querySelectorAll('g.opt').length === 5);
    clk(opt('expand')); await sleep(6000);
    ok('desplegar', nodes.length === 6 && opt('expand').classList.contains('off'));
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
    clk(document.getElementById('svg')); await sleep(200);
    ok('fondo cierra', !document.querySelector('g.opt') && selId == null);
    cmd('/form x'); await sleep(200); ok('comando erróneo', $('q').classList.contains('err'));
    cmd('/from Marea to Michael Jackson'); await sleep(25000);
    ok('camino', nodes.length > 5 && links.every(l => l.path));
    $('clear').click(); await sleep(300);
    ok('clear', nodes.length === 0 && player.paused && !player.getAttribute('src'));
  } catch (e) { r.push('EXCEPCION ' + e.message); }
  document.title = r.join(' | ');
}, 500);
