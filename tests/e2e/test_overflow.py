"""Mesure reelle dans le HTML livre : aucun texte ne deborde de sa carte, nom et type ne se touchent pas (reprise d'overflow_test.py)."""
import pytest

JS = '''(view) => {
  const v = document.querySelector('.view[data-view="' + view + '"]'); if (!v) return null; v.hidden = false;
  const out = [];
  for (const T of v.querySelectorAll('.tbl')) {
    const card = T.querySelector('.card-bg').getBBox(), right = card.x + card.width;
    for (const t of T.querySelectorAll('text')) {
      const b = t.getBBox();
      if (b.x + b.width > right - 2 || b.x < card.x + 1) out.push(T.dataset.table + ' : "' + t.textContent + '" deborde');
    }
    for (const row of T.querySelectorAll('.col')) {
      const n = row.querySelector('.cn').getBBox(), ty = row.querySelector('.ct').getBBox();
      if (n.x + n.width > ty.x - 4) out.push(T.dataset.table + '.' + row.dataset.col + ' : nom et type se touchent');
    }
  }
  v.hidden = view !== 'all';
  return out;
}'''


@pytest.mark.parametrize('view', ['all', 'keys', 'names', 'all-full', 'all-frames'])
def test_aucun_debordement(page, demo, view):
    page.goto((demo['out'] / 'DEMO.html').as_uri())
    r = page.evaluate(JS, view)
    assert r == [], r[:8]
