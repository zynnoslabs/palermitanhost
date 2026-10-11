// ### CAMBIO AQUÍ ### — País → Provincia/Estado → Ciudad, con las opciones de cada país.
// Si algo no carga (sin internet, país sin datos), los campos quedan para escribir a mano.
(function () {
  var box = document.getElementById('ubicacion');
  if (!box) return;
  var pais = document.getElementById('pais'),
      sel = document.getElementById('provincia-sel'),
      prov = document.getElementById('provincia'),
      ciudad = document.getElementById('ciudad'),
      dlCiudades = document.getElementById('dl-ciudades'),
      dlBarrios = document.getElementById('dl-barrios'),
      base = (document.querySelector('script[src*="ubicacion.js"]').src || '').replace(/ubicacion\.js.*$/, 'geo/'),
      datos = null, cache = {};

  function opciones(dl, lista) {
    dl.innerHTML = '';
    (lista || []).forEach(function (n) { var o = document.createElement('option'); o.value = n; dl.appendChild(o); });
  }
  function codigoProvincia() {
    var o = sel.options[sel.selectedIndex];
    return o ? o.getAttribute('data-c') : null;
  }
  function alCambiarProvincia(inicial) {
    prov.value = sel.value;
    var c = codigoProvincia();
    var lista = (datos && datos.c && datos.c[c]) || [];
    opciones(dlCiudades, lista);
    opciones(dlBarrios, (datos && datos.b && datos.b[c]) || []);
    if (!inicial) {
      // Ciudad Autónoma de Buenos Aires: la ciudad es Buenos Aires; si no, se elige de la lista
      ciudad.value = (lista.length === 1) ? lista[0] : '';
      if (!ciudad.value) ciudad.focus();
    }
  }
  function mostrarSelect(si) {
    sel.style.display = si ? '' : 'none';
    prov.type = si ? 'hidden' : 'text';
  }
  function cargarPais(inicial) {
    var cc = pais.value;
    var listo = function (d) {
      datos = d;
      if (!d || !d.e || !d.e.length) { mostrarSelect(false); opciones(dlCiudades, []); return; }
      sel.innerHTML = '<option value="">— Elegí —</option>';
      var actual = inicial ? box.getAttribute('data-provincia') : '';
      d.e.forEach(function (e) {
        var o = document.createElement('option');
        o.value = e[1]; o.textContent = e[1]; o.setAttribute('data-c', e[0]);
        if (actual && e[1].toLowerCase() === actual.toLowerCase()) o.selected = true;
        sel.appendChild(o);
      });
      mostrarSelect(true);
      if (actual && !sel.value) {   // provincia escrita a mano que no está en la lista: se conserva
        var o = document.createElement('option'); o.value = actual; o.textContent = actual; o.selected = true;
        sel.appendChild(o);
      }
      alCambiarProvincia(inicial);
    };
    if (!inicial) { prov.value = ''; ciudad.value = ''; }
    if (cache[cc] !== undefined) return listo(cache[cc]);
    fetch(base + cc + '.json').then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })
      .then(function (d) { cache[cc] = d; listo(d); });
  }
  pais.addEventListener('change', function () { cargarPais(false); });
  sel.addEventListener('change', function () { alCambiarProvincia(false); });
  // Argentina sin provincia elegida (propiedad nueva): Ciudad Autónoma de Buenos Aires por defecto
  if (!box.getAttribute('data-provincia') && pais.value === 'AR' && ciudad.value === 'Buenos Aires') {
    box.setAttribute('data-provincia', 'Ciudad Autónoma de Buenos Aires');
  }
  cargarPais(true);
})();
