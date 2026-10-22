

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

// ### CAMBIO AQUÍ ### — SKELETONS: mientras carga la página siguiente se ve la forma del contenido
// (bloques grises que brillan) en vez de una pantalla quieta. Solo aparece si tarda más de 0,15 s.
(function () {
  var DESCARGAS = /\/(respaldo\/descargar|archivo-anual\/|informes\/\d+\/(pdf|excel))|\.(zip|pdf|xlsx|csv)(\?|$)/i;
  var timer = null, corte = null;
  function capa() {
    var main = document.querySelector('main.main');
    if (!main || main.classList.contains('cargando-pagina')) return;
    var c = document.createElement('div');
    c.className = 'sk-capa';
    c.setAttribute('role', 'status');
    c.innerHTML = '<span class="solo-lector">Cargando…</span>' +
      '<div class="sk sk-titulo"></div>' +
      '<div class="sk-grilla"><div class="sk sk-tarjeta"></div><div class="sk sk-tarjeta"></div><div class="sk sk-tarjeta"></div></div>' +
      '<div class="sk sk-bloque"></div>' +
      '<div class="sk sk-linea" style="width:90%"></div><div class="sk sk-linea" style="width:75%"></div><div class="sk sk-linea" style="width:60%"></div>';
    main.classList.add('cargando-pagina');
    main.setAttribute('aria-busy', 'true');
    main.appendChild(c);
    corte = setTimeout(sacar, 10000);   // si algo falla, a los 10 s vuelve a mostrar la página
  }
  function sacar() {
    clearTimeout(timer); clearTimeout(corte); timer = null;
    var main = document.querySelector('main.main');
    if (!main) return;
    main.classList.remove('cargando-pagina');
    main.removeAttribute('aria-busy');
    var c = main.querySelector('.sk-capa'); if (c) c.remove();
  }
  function programar() { clearTimeout(timer); timer = setTimeout(capa, 150); }
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
    var url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    if (url.origin !== location.origin || DESCARGAS.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;   // salto dentro de la misma página
    programar();
  });
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (f.hasAttribute('data-sin-carga')) return;
    var dest = f.getAttribute('action') || location.pathname;
    if (DESCARGAS.test(dest)) return;
    setTimeout(function () { if (!e.defaultPrevented) programar(); }, 0);   // si un confirm() lo canceló, no se muestra
  });
  window.addEventListener('pageshow', sacar);
})();

// ### CAMBIO AQUÍ ### — ACCESIBILIDAD: cada etiqueta queda unida a su campo (el lector de pantalla
// lee "Desde" al entrar al campo y tocar la etiqueta pone el cursor en el campo)
(function () {
  function unir() {
    var n = 0;
    document.querySelectorAll('label:not([for])').forEach(function (l) {
      if (l.querySelector('input, select, textarea')) return;
      var g = l.parentElement; if (!g) return;
      var c = g.querySelector('input:not([type=hidden]), select, textarea');
      if (!c || (c.labels && c.labels.length) || c.getAttribute('aria-label')) return;
      if (!c.id) c.id = 'campo-' + (++n) + '-' + Math.random().toString(36).slice(2, 6);
      l.setAttribute('for', c.id);
    });
    // campos de filtro sin etiqueta visible: se usa el texto de la primera opción
    document.querySelectorAll('select:not([aria-label])').forEach(function (s) {
      if (s.labels && s.labels.length) return;
      var t = s.name === 'propiedad_id' || s.name === 'pid' ? 'Propiedad' : (s.options[0] ? s.options[0].text.trim() : '');
      if (t) s.setAttribute('aria-label', t);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', unir); else unir();
})();

// ### CAMBIO AQUÍ ### — gráficos: textos y líneas de fondo con los colores del tema (claro u oscuro)
(function () {
  if (typeof Chart === 'undefined' || typeof tk !== 'function') return;
  Chart.defaults.color = tk('--color-text-2');
  Chart.defaults.borderColor = tk('--color-border-soft');
})();

// ### CAMBIO AQUÍ ### — el logo se anima una sola vez por sesión (no en cada página)
(function () {
  var l = document.getElementById('marca-logo');
  if (!l) return;
  var visto = false;
  try { visto = sessionStorage.getItem('ph-logo') === '1'; sessionStorage.setItem('ph-logo', '1'); } catch (e) { visto = true; }
  if (!visto) l.classList.add('anim');
})();

// ### CAMBIO AQUÍ ### — instalable en el celular (PWA)
// (el registro del service worker está en templates/_ajustes_head.html, así también corre en el login)
var pedidoInstalar = null;
window.addEventListener('beforeinstallprompt', function (e) {
  e.preventDefault(); pedidoInstalar = e;
  var b = document.getElementById('instalar-app'); if (b) b.hidden = false;
});
document.addEventListener('click', function (e) {
  if (!e.target.closest || !e.target.closest('#instalar-app') || !pedidoInstalar) return;
  pedidoInstalar.prompt(); pedidoInstalar = null; e.target.closest('#instalar-app').hidden = true;
});
