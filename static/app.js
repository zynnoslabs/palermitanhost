

// ### CAMBIO AQUÍ ### — ícono "i": muestra la explicación al pasar el mouse o al tocarlo (celular)
(function () {
  var tip = document.createElement('div');
  tip.className = 'tip-flotante';
  tip.setAttribute('role', 'tooltip');
  document.addEventListener('DOMContentLoaded', function () { document.body.appendChild(tip); });
  var actual = null, desde = 0;
  function mostrar(el) {
    if (actual !== el) desde = Date.now();
    if (!tip.parentNode) document.body.appendChild(tip);
    actual = el;
    tip.textContent = el.getAttribute('data-tip') || '';
    tip.style.display = 'block';
    var r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight, m = 8;
    var x = Math.min(Math.max(m, r.left + r.width / 2 - w / 2), window.innerWidth - w - m);
    var y = r.top - h - 8;
    if (y < m) y = r.bottom + 8;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  function ocultar() { tip.style.display = 'none'; actual = null; }
  function buscar(e) { return e.target && e.target.closest ? e.target.closest('.info') : null; }
  // en pantallas táctiles el navegador simula movimientos de mouse después de cada toque: se ignoran
  var toque = 0;
  document.addEventListener('touchstart', function () { toque = Date.now(); }, {passive: true, capture: true});
  function esToque() { return Date.now() - toque < 1000; }
  document.addEventListener('mouseover', function (e) { var el = buscar(e); if (el && !esToque()) mostrar(el); });
  document.addEventListener('mouseout', function (e) { var el = buscar(e); if (el && !esToque() && !el.contains(e.relatedTarget)) ocultar(); });
  document.addEventListener('focusin', function (e) { var el = buscar(e); if (el) mostrar(el); });
  document.addEventListener('focusout', function (e) { if (buscar(e)) ocultar(); });
  // Tocar el "i" no dispara el botón o link que lo contiene
  document.addEventListener('click', function (e) {
    var el = buscar(e);
    // en el celular el toque ya lo mostró (mouseover/focus): no ocultarlo en el mismo toque
    if (el) { e.preventDefault(); e.stopPropagation(); if (actual === el && Date.now() - desde > 500) ocultar(); else mostrar(el); return; }
    ocultar();
  }, true);
  window.addEventListener('scroll', ocultar, true);
  window.addEventListener('resize', ocultar);
})();

// ### CAMBIO AQUÍ ### — menú lateral en el celular
function toggleMenu(abrir) {
  var sb = document.querySelector('.sidebar'), fondo = document.querySelector('.menu-fondo');
  if (!sb) return;
  var abierto = abrir === undefined ? !sb.classList.contains('open') : abrir;
  sb.classList.toggle('open', abierto);
  if (fondo) fondo.classList.toggle('visible', abierto);
}

// ### CAMBIO AQUÍ ### — evita el doble toque: al enviar un formulario, sus botones se desactivan
// (antes, tocar dos veces "Guardar" o "Generar" creaba duplicados y gastaba la IA dos veces).
document.addEventListener('submit', function (e) {
  var f = e.target;
  if (e.defaultPrevented || (f.method || '').toLowerCase() !== 'post') return;
  if (f.dataset.enviando === '1') { e.preventDefault(); return; }
  f.dataset.enviando = '1';
  setTimeout(function () {   // después de armar los datos del formulario
    f.querySelectorAll('button[type=submit], button:not([type]), input[type=submit]').forEach(function (b) {
      b.disabled = true;
      b.dataset.textoOriginal = b.textContent;
      if (b.textContent.trim().length > 2) b.textContent = f.dataset.procesando || 'Procesando…';
    });
  }, 0);
});
// al volver con "atrás" el navegador puede mostrar la página guardada con los botones apagados
window.addEventListener('pageshow', function () {
  document.querySelectorAll('form[data-enviando]').forEach(function (f) {
    delete f.dataset.enviando;
    f.querySelectorAll('button, input[type=submit]').forEach(function (b) {
      b.disabled = false;
      if (b.dataset.textoOriginal) b.textContent = b.dataset.textoOriginal;
    });
  });
});

// ### CAMBIO AQUÍ ### — al llegar desde una alerta (?resaltar=...), lo que hay que revisar se ilumina
// unos segundos y la página se mueve hasta ahí. No queda nada seleccionado.
(function () {
  var params = new URLSearchParams(location.search);
  var claves = (params.get('resaltar') || '').split(',').filter(Boolean);
  if (!claves.length) return;
  function iluminar() {
    var els = [];
    claves.forEach(function (k) {
      var sel = '#' + (window.CSS && CSS.escape ? CSS.escape(k) : k) + ', [name="' + k + '"], [data-resaltar~="' + k + '"]';
      var hallados = [];
      try { hallados = document.querySelectorAll(sel); } catch (err) { return; }   // dirección rara: se ignora
      hallados.forEach(function (e) {
        var caja = (e.matches('input, select, textarea') && e.closest('.form-group')) || e;
        if (els.indexOf(caja) < 0) els.push(caja);
      });
    });
    if (!els.length) return;
    // ### CAMBIO AQUÍ ### si está dentro de algo plegado ("Ver cómo se calculó"), se abre
    els.forEach(function (e) {
      for (var d = e; d; d = d.parentElement) { if (d.tagName === 'DETAILS') d.open = true; }
    });
    els[0].scrollIntoView({behavior: 'smooth', block: 'center'});
    els.forEach(function (e) { e.classList.add('resaltado'); });
    setTimeout(function () { els.forEach(function (e) { e.classList.remove('resaltado'); }); }, 3500);
    // se saca el parámetro de la dirección: al recargar no vuelve a titilar
    params.delete('resaltar');
    var q = params.toString();
    history.replaceState(null, '', location.pathname + (q ? '?' + q : '') + location.hash);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iluminar);
  else iluminar();
})();
