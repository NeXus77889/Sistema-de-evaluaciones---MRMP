/* Buscador de destinatarios para Mensajería.
 * Convierte el <select id="id_destinatario"> en una lista con búsqueda,
 * filtro por rol y etiquetas. El <select> sigue siendo el campo real. */
(function () {
  'use strict';

  var ROLES = {
    ADMIN: { label: 'Autoridad / Administrador', plural: 'Autoridades', order: 0 },
    DOCENTE: { label: 'Docente', plural: 'Docentes', order: 1 },
    ESTUDIANTE: { label: 'Estudiante', plural: 'Estudiantes', order: 2 }
  };

  function normalize(text) {
    return (text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function init(select) {
    var people = [];
    Array.prototype.forEach.call(select.options, function (opt) {
      if (!opt.value) return;
      var rol = opt.getAttribute('data-rol') || '';
      people.push({
        value: opt.value,
        name: opt.textContent.trim(),
        rol: rol,
        curso: opt.getAttribute('data-curso') || '',
        haystack: normalize(opt.textContent + ' ' + ((ROLES[rol] || {}).label || '') + ' ' + (opt.getAttribute('data-curso') || ''))
      });
    });
    if (!people.length) return;

    people.sort(function (a, b) {
      var ra = (ROLES[a.rol] || { order: 9 }).order;
      var rb = (ROLES[b.rol] || { order: 9 }).order;
      return ra - rb || a.name.localeCompare(b.name, 'es');
    });

    var rolesPresentes = [];
    people.forEach(function (p) {
      if (ROLES[p.rol] && rolesPresentes.indexOf(p.rol) === -1) rolesPresentes.push(p.rol);
    });

    var activeRole = '';
    var query = '';
    var highlighted = -1;
    var visible = [];

    var root = el('div', 'up');
    var selected = el('div', 'up-selected');
    var filters = el('div', 'up-filters');
    var search = el('input', 'up-search');
    search.type = 'search';
    search.placeholder = 'Buscar por nombre, cargo o curso...';
    search.setAttribute('aria-label', 'Buscar destinatario');
    search.autocomplete = 'off';
    var list = el('div', 'up-list');
    list.setAttribute('role', 'listbox');
    var count = el('div', 'up-count');

    if (rolesPresentes.length > 1) {
      var buttons = [{ key: '', text: 'Todos' }].concat(rolesPresentes.map(function (r) {
        return { key: r, text: ROLES[r].plural };
      }));
      buttons.forEach(function (b) {
        var btn = el('button', 'up-chip', b.text);
        btn.type = 'button';
        btn.setAttribute('data-role', b.key);
        btn.addEventListener('click', function () {
          activeRole = b.key;
          highlighted = -1;
          render();
        });
        filters.appendChild(btn);
      });
    }

    root.appendChild(selected);
    if (filters.children.length) root.appendChild(filters);
    root.appendChild(search);
    root.appendChild(list);
    root.appendChild(count);
    select.style.display = 'none';
    select.parentNode.insertBefore(root, select.nextSibling);

    function badge(rol) {
      var info = ROLES[rol];
      var span = el('span', 'up-badge up-badge-' + (rol || 'otro').toLowerCase(), info ? info.label : 'Usuario');
      return span;
    }

    function renderSelected() {
      selected.textContent = '';
      var current = people.filter(function (p) { return p.value === select.value; })[0];
      if (!current) {
        selected.appendChild(el('span', 'up-placeholder', 'Ningún destinatario seleccionado'));
        return;
      }
      selected.appendChild(el('strong', null, current.name));
      selected.appendChild(badge(current.rol));
      if (current.curso) selected.appendChild(el('span', 'up-course', current.curso));
      var clear = el('button', 'up-clear', '×');
      clear.type = 'button';
      clear.setAttribute('aria-label', 'Quitar destinatario');
      clear.addEventListener('click', function () {
        select.value = '';
        select.dispatchEvent(new Event('change', { bubbles: true }));
        render();
      });
      selected.appendChild(clear);
    }

    function choose(person) {
      select.value = person.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      render();
    }

    function render() {
      var terms = normalize(query).split(/\s+/).filter(Boolean);
      visible = people.filter(function (p) {
        if (activeRole && p.rol !== activeRole) return false;
        return terms.every(function (t) { return p.haystack.indexOf(t) !== -1; });
      });

      Array.prototype.forEach.call(filters.children, function (btn) {
        btn.classList.toggle('is-active', btn.getAttribute('data-role') === activeRole);
      });

      list.textContent = '';
      visible.slice(0, 80).forEach(function (p, i) {
        var row = el('div', 'up-row');
        row.setAttribute('role', 'option');
        if (p.value === select.value) row.classList.add('is-selected');
        if (i === highlighted) row.classList.add('is-highlighted');
        var main = el('div', 'up-row-main');
        main.appendChild(el('span', 'up-name', p.name));
        main.appendChild(badge(p.rol));
        row.appendChild(main);
        if (p.curso) row.appendChild(el('div', 'up-course', p.curso));
        row.addEventListener('mousedown', function (ev) {
          ev.preventDefault();
          choose(p);
        });
        list.appendChild(row);
      });
      if (!visible.length) list.appendChild(el('div', 'up-empty', 'Sin resultados'));

      count.textContent = visible.length > 80
        ? 'Mostrando 80 de ' + visible.length + '. Escribe más para afinar.'
        : visible.length + ' resultado' + (visible.length === 1 ? '' : 's');
      renderSelected();
    }

    search.addEventListener('input', function () {
      query = search.value;
      highlighted = visible.length ? 0 : -1;
      render();
    });

    search.addEventListener('keydown', function (ev) {
      var shown = Math.min(visible.length, 80);
      if (ev.key === 'ArrowDown') {
        ev.preventDefault();
        highlighted = Math.min(highlighted + 1, shown - 1);
        render();
      } else if (ev.key === 'ArrowUp') {
        ev.preventDefault();
        highlighted = Math.max(highlighted - 1, 0);
        render();
      } else if (ev.key === 'Enter') {
        if (highlighted >= 0 && visible[highlighted]) {
          ev.preventDefault();
          choose(visible[highlighted]);
        }
      }
      var active = list.querySelector('.is-highlighted');
      if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
    });

    render();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var select = document.getElementById('id_destinatario');
    if (select && select.tagName === 'SELECT') init(select);
  });
})();
