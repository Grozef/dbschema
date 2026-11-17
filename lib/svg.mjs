// layout.json + model.json -> SVG (cartes facon MySQL Workbench, notation pattes d'oie + cardinalites texte).
export const HEAD = 26, ROW = 22, FOOT = 26;
const PALETTE = ['#98BFDA', '#9FD39B', '#F2C48D', '#C7B3E5', '#8FD3D1', '#E9A3B8', '#BDBDBD', '#E6D58A', '#A9C4EB'];
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export function groupColors(model) {
  const out = {};
  Object.keys(model.groups ?? {}).forEach((g, i) => { out[g] = PALETTE[i % PALETTE.length]; });
  return out;
}

function icon(c, x, y) {
  // cle jaune (PK), losange rouge (FK), losange bleu plein (NOT NULL) ou vide (nullable)
  if (c.pk) return `<g transform="translate(${x},${y})"><circle cx="3.5" cy="5.5" r="3" fill="#F5C518" stroke="#9A7B00" stroke-width=".8"/><path d="M6 5.5h5.5v2.2M9.5 5.5v1.8" stroke="#9A7B00" stroke-width="1.3" fill="none"/></g>`;
  const fill = c.fk ? (c.nullable ? '#fff' : '#D9534F') : (c.nullable ? '#fff' : '#4A90D9');
  const stroke = c.fk ? '#B52B27' : '#2F6DB5';
  return `<path transform="translate(${x},${y})" d="M5.5 1L10 5.5 5.5 10 1 5.5Z" fill="${fill}" stroke="${stroke}" stroke-width="1"/>`;
}

// Extremite d'un lien : (x,y) point sur la carte, (dx,dy) direction unitaire VERS l'exterieur de la carte
function endMarker(kind, x, y, dx, dy) {
  const px = -dy, py = dx; // perpendiculaire
  const at = (d, o) => [x + dx * d + px * o, y + dy * d + py * o];
  const line = (a, b) => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`;
  const bar = (d) => line(at(d, -6), at(d, 6));
  const circle = (d) => { const c = at(d, 0); return `<circle cx="${c[0]}" cy="${c[1]}" r="4" fill="var(--bg)"/>`; };
  const crow = () => line(at(10, 0), at(0, -7)) + line(at(10, 0), at(0, 7)) + line(at(10, 0), at(0, 0));
  switch (kind) {
    case '1': return bar(6) + bar(10);          // exactement un
    case '0..1': return bar(6) + circle(14);    // zero ou un
    case '0..N': return crow() + circle(14);    // zero ou plusieurs
    case '1..N': return crow() + bar(13);       // un ou plusieurs
    default: return '';
  }
}

const dir = (a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1; return [dx / l, dy / l]; };

export function renderSvg(model, layout, { idPrefix = '' } = {}) {
  const colors = groupColors(model);
  const W = Math.ceil(layout.width), H = Math.ceil(layout.height);
  const parts = [`<svg xmlns="http://www.w3.org/2000/svg" class="erd" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="Tahoma, 'Segoe UI', sans-serif">`];
  parts.push(`<rect class="bgfill" x="0" y="0" width="${W}" height="${H}"/>`);
  for (const [g, r] of Object.entries(layout.groups)) {
    parts.push(`<g class="grp" data-group="${esc(g)}"><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="10" fill="${colors[g]}" fill-opacity=".13" stroke="${colors[g]}" stroke-width="1.5"/>`
      + `<text x="${r.x + 14}" y="${r.y + 26}" class="grp-label" fill="${colors[g]}">${esc(g)}</text></g>`);
  }
  // liens routes
  for (const e of layout.edges) {
    const p = e.points;
    if (p.length < 2) continue;
    const d = 'M' + p.map((q) => q.join(',')).join('L');
    const ds = dir(p[1], p[0]), dt = dir(p[p.length - 2], p[p.length - 1]);
    parts.push(`<g class="rel" data-rel="${e.id}" data-from="${esc(e.from)}" data-to="${esc(e.to)}">`
      + `<path class="hit" d="${d}"/><path class="ln" d="${d}"/>`
      + `<g class="mk">${endMarker(e.card_child, p[0][0], p[0][1], -ds[0], -ds[1])}${endMarker(e.card_parent, p.at(-1)[0], p.at(-1)[1], -dt[0], -dt[1])}</g>`
      + e.labels.map((l) => `<text class="card" x="${l.x + l.w / 2}" y="${l.y + l.h - 3}" text-anchor="middle">${esc(l.text)}</text>`).join('')
      + `</g>`);
  }
  // liens split : amorce + nom de la table cible
  for (const s of layout.splits) {
    const sign = s.side === 'EAST' ? 1 : -1, x2 = s.x + sign * 16;
    parts.push(`<g class="rel split" data-rel="${s.id}" data-from="${esc(s.from)}" data-to="${esc(s.to)}">`
      + `<path class="hit" d="M${s.x},${s.y}H${x2}"/><path class="ln" d="M${s.x},${s.y}H${x2}"/>`
      + `<g class="mk">${endMarker(s.card_child, s.x, s.y, sign, 0)}</g></g>`);
  }
  // cartes
  for (const [name, r] of Object.entries(layout.tables)) {
    const t = model.tables[name];
    const col = r.group ? colors[r.group] : '#98BFDA';
    const cols = r.rows.map((n) => t.columns.find((c) => c.name === n));
    const rows = cols.map((c, i) => {
      const y = r.y + HEAD + ROW * i;
      const type = c.type.toUpperCase().replace(/ UNSIGNED/, '');
      return `<g class="col${c.pk ? ' pk' : ''}${c.fk ? ' fk' : ''}" data-col="${esc(c.name)}">`
        + `<rect class="rowbg" x="${r.x + 1}" y="${y}" width="${r.w - 2}" height="${ROW}"/>`
        + icon(c, r.x + 8, y + 5.5)
        + `<text x="${r.x + 24}" y="${y + 15}" class="cn">${esc(c.name)}${layout.splitTag?.[name + '.' + c.name] ? `<tspan class="split-tag" dx="8">${esc(layout.splitTag[name + '.' + c.name])}</tspan>` : ''}</text>`
        + `<text x="${r.x + r.w - 8}" y="${y + 15}" class="ct" text-anchor="end">${esc(type)}</text></g>`;
    }).join('');
    const nIdx = t.indexes.length;
    parts.push(`<g class="tbl" data-table="${esc(name)}" data-group="${esc(r.group ?? '')}">`
      + `<rect class="card-bg" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="3"/>`
      + `<path d="M${r.x},${r.y + HEAD}V${r.y + 3}q0,-3 3,-3H${r.x + r.w - 3}q3,0 3,3V${r.y + HEAD}Z" fill="${col}"/>`
      + `<text x="${r.x + 8}" y="${r.y + 17}" class="tn">${esc(name)}${layout.splitTag?.__head?.[name] ? `<tspan class="split-tag" dx="8">${esc(layout.splitTag.__head[name])}</tspan>` : ''}</text>`
      + rows
      + (layout.mode === 'names' ? '' : `<rect class="foot" x="${r.x + 1}" y="${r.y + r.h - FOOT}" width="${r.w - 2}" height="${FOOT - 1}"/>`
      + `<text x="${r.x + 8}" y="${r.y + r.h - 9}" class="ix">Indexes (${nIdx})${layout.mode === 'keys' && t.columns.length > cols.length ? ' &#183; +' + (t.columns.length - cols.length) + ' col.' : ''}</text>`)
      + `<rect class="card-bd" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="3"/></g>`);
  }
  parts.push('</svg>');
  return parts.join('\n');
}

export const SVG_CSS = `
.erd{--bg:#fff;--ink:#1f2328;--mute:#6a737d;--line:#5b6573;--bd:#8aa4bf;--row:#fff;--foot:#eef1f4}
.erd .bgfill{fill:var(--bg)}
.erd .grp-label{font-size:15px;font-weight:700;letter-spacing:.06em}
.erd .card-bg{fill:var(--row)} .erd .card-bd{fill:none;stroke:var(--bd);stroke-width:1}
.erd .tn{font-size:12px;font-weight:700;fill:#10233a}
.erd .rowbg{fill:transparent} .erd .cn{font-size:11px;fill:var(--ink)} .erd .ct{font-size:11px;fill:var(--mute)}
.erd .col.pk .cn{font-weight:700}
.erd .foot{fill:var(--foot)} .erd .ix{font-size:10.5px;fill:var(--mute)}
.erd .rel .ln{fill:none;stroke:var(--line);stroke-width:1.3}
.erd .rel .hit{fill:none;stroke:transparent;stroke-width:9}
.erd .rel .mk{stroke:var(--line);stroke-width:1.3;fill:none}
.erd .card{font-size:10.5px;font-weight:700;fill:#8a3b12}
.erd .split-tag{font-size:10px;fill:#8a3b12;font-style:italic}
.erd .split .ln{stroke-dasharray:4 3}
`;
