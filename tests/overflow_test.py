"""Mesure reelle (Chrome) : un texte de carte depasse-t-il le bord de sa carte, ou chevauche-t-il le texte voisin (nom / type) ?"""
import os, sys, pathlib
from playwright.sync_api import sync_playwright
# Chrome installe (DBSCHEMA_CHROME pour un autre chemin) ; a defaut, le Chromium de Playwright
CHROME = os.environ.get('DBSCHEMA_CHROME') or next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') if os.path.exists(p)), None)
html = pathlib.Path(sys.argv[1]).resolve()
JS = '''(view) => {
  const v = document.querySelector('.view[data-view="' + view + '"]'); if (!v) return null; v.hidden = false;
  const out = [];
  for (const T of v.querySelectorAll('.tbl')) {
    const card = T.querySelector('.card-bg').getBBox(), right = card.x + card.width;
    for (const t of T.querySelectorAll('text')) {
      const b = t.getBBox();
      if (b.x + b.width > right - 2 || b.x < card.x + 1) out.push(T.dataset.table + ' : "' + t.textContent + '" deborde (' + Math.round(b.x + b.width - right) + ' px)');
    }
    for (const row of T.querySelectorAll('.col')) {
      const n = row.querySelector('.cn').getBBox(), ty = row.querySelector('.ct').getBBox();
      if (n.x + n.width > ty.x - 4) out.push(T.dataset.table + '.' + row.dataset.col + ' : nom et type se touchent (' + Math.round(n.x + n.width - ty.x) + ' px)');
    }
  }
  v.hidden = view !== 'all';
  return out;
}'''
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_page()
    pg.goto(html.as_uri())
    for view in ['all', 'keys', 'names', 'all-full', 'all-frames']:
        r = pg.evaluate(JS, view)
        if r is None:
            continue  # vue non produite (sans --frames, sans hub)
        print(f'[{"OK" if not r else "ECHEC"}] vue {view} : {len(r)} debordement(s)')
        for x in r[:8]: print('    ' + x)
        bad += len(r)
    b.close()
sys.exit(1 if bad else 0)
