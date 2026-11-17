"""Mise en page dbschema -> MySQL Workbench. Workbench n'est JAMAIS lance ici (mono-instance : un --run-script part dans la
session ouverte de l'utilisateur, incident du 2026-11-17).

  script <layout.json> <sortie.py>             script GRT a lancer PAR L'UTILISATEUR : Scripting > Run Workbench Script File...
                                              (place les tables par nom, drawSplit sur les liens vers les tables hub ; rien d'autre)
  patch  <layout.json> <source.mwb> <sortie.mwb>  copie du modele : seuls left/top des tables, drawSplit et taille du diagramme
                                              changent ; la source n'est pas modifiee (SHA-256 verifie, sortie != source).

Les tailles des tables dans Workbench dependent du modele (lignes de 22 px dans un modele, 25 px dans un autre) : les positions
du layout sont mises a l'echelle par le rapport max (taille Workbench / taille du layout), ce qui conserve tous les ecarts
(aucun chevauchement possible si le layout n'en a pas), puis un controle de chevauchement est fait sur les tailles reelles.
"""
import hashlib, json, os, re, sys, zipfile

MARGIN = 40


def load(p):
    return json.load(open(p, encoding='utf-8'))


def boxes(layout):
    return {n: (t['x'], t['y'], t['w'], t['h']) for n, t in layout['tables'].items()}


def scaled(box, real):
    """Positions mises a l'echelle des tailles reelles : rx, ry >= 1 tels que chaque table reelle tienne dans sa place."""
    rx = max([1] + [real[n][0] / box[n][2] for n in real if n in box])
    ry = max([1] + [real[n][1] / box[n][3] for n in real if n in box])
    return {n: (round(b[0] * rx), round(b[1] * ry)) for n, b in box.items()}, rx, ry


def cmd_script(layout_path, out):
    lay = load(layout_path)
    box, hubs = boxes(lay), lay.get('hubs', [])
    src = f'''# -*- coding: utf-8 -*-
# Genere par dbschema. A lancer dans MySQL Workbench : Scripting > Run Workbench Script File...
# Place les tables par nom et dessine en "split" les liens vers : {", ".join(hubs) or "(aucune)"}.
# Ne cree, ne ferme et n'enregistre rien (File > Save pour garder). Annulation par Ctrl+Z non verifiee : essayer sur une copie.
import grt
BOX = {json.dumps({n: [round(v, 1) for v in b] for n, b in box.items()})}  # x, y, largeur, hauteur du layout dbschema
HUBS = {json.dumps(hubs)}
model = grt.root.wb.doc.physicalModels[0]
placed, split, missing = 0, 0, set(BOX)
for d in model.diagrams:
    figs = [f for f in d.figures if getattr(f, 'table', None) and f.table.name in BOX]
    # mise a l'echelle par les tailles reelles (hauteur de ligne variable selon le modele) : les ecarts sont conserves
    rx = max([1] + [f.width / BOX[f.table.name][2] for f in figs])
    ry = max([1] + [f.height / BOX[f.table.name][3] for f in figs])
    right = bottom = 0
    for f in figs:
        b = BOX[f.table.name]
        f.left, f.top = round(b[0] * rx), round(b[1] * ry)
        placed += 1
        missing.discard(f.table.name)
        right, bottom = max(right, f.left + f.width), max(bottom, f.top + f.height)
    over = [(a.table.name, b.table.name) for i, a in enumerate(figs) for b in figs[i + 1:]
            if a.left < b.left + b.width and b.left < a.left + a.width and a.top < b.top + b.height and b.top < a.top + a.height]
    if over:
        print('dbschema : ATTENTION chevauchements %s' % over)
    for c in d.connections:
        fk = getattr(c, 'foreignKey', None)
        if fk and fk.referencedTable and fk.referencedTable.name in HUBS and fk.owner.name != fk.referencedTable.name:
            c.drawSplit = 1
            split += 1
    if d.width < right + {MARGIN}:
        d.width = right + {MARGIN}
    if d.height < bottom + {MARGIN}:
        d.height = bottom + {MARGIN}
print('dbschema : %d tables placees, %d liens en split, absentes du diagramme : %s' % (placed, split, ', '.join(sorted(missing)) or 'aucune'))
'''
    open(out, 'w', encoding='utf-8').write(src)
    print(f'script Workbench : {out} ({len(box)} tables, hubs={hubs or "-"})')


def own_value(x, struct, key):
    """Valeurs `key` propres (a l'indentation des membres) de chaque objet `struct` : liste de (debut, fin, valeur)."""
    out = []
    for m in re.finditer(r'\n( *)<value type="object" struct-name="%s" id="' % re.escape(struct), x):
        mm = re.compile(r'\n {%d}<value type="real" key="%s">([-\d.e]+)<' % (len(m.group(1)) + 2, key)).search(x, m.end())
        if mm:
            out.append((mm.start(1), mm.end(1), float(mm.group(1))))
    return out


def cmd_patch(layout_path, src, dst):
    if os.path.exists(dst) and os.path.samefile(src, dst):
        sys.exit('ECHEC : la sortie est la source (%s) : refus, la source serait ecrasee' % dst)
    lay = load(layout_path)
    box, hubs = boxes(lay), set(lay.get('hubs', []))
    h0 = hashlib.sha256(open(src, 'rb').read()).hexdigest()
    with zipfile.ZipFile(src) as zin:
        x = zin.read('document.mwb.xml').decode('utf-8')
        others = [(it, zin.read(it.filename)) for it in zin.infolist() if it.filename != 'document.mwb.xml']
        doc_info = zin.getinfo('document.mwb.xml')
    if x.count('struct-name="workbench.physical.Layer"') > 1:
        sys.exit('ECHEC : le modele a plusieurs calques (layers) ; les positions y sont relatives au calque. Non gere : refus.')

    # tables : id -> nom ; FK : id -> (table proprietaire, table referencee)
    # nom PROPRE de la table = la cle "name" a l'indentation de ses membres (les colonnes, imbriquees, ont aussi un "name")
    tname = {}
    for m in re.finditer(r'\n( *)<value type="object" struct-name="db\.mysql\.Table" id="(\{[^}]+\})"', x):
        ind = len(m.group(1)) + 2
        tname[m.group(2)] = re.compile(r'\n {%d}<value type="string" key="name">([^<]*)</value>' % ind).search(x, m.end()).group(1)
    fkref = {}
    for m in re.finditer(r'<value type="object" struct-name="db\.mysql\.ForeignKey" id="(\{[^}]+\})"', x):
        end = x.find('struct-name="db.mysql.ForeignKey" id=', m.end())
        blk = x[m.start(): end if end > 0 else len(x)]
        ref = re.search(r'key="referencedTable">(\{[^}]+\})<', blk)
        own = re.search(r'key="owner">(\{[^}]+\})<', blk)
        fkref[m.group(1)] = (tname.get(own.group(1)) if own else None, tname.get(ref.group(1)) if ref else None)

    spans = []
    for m in re.finditer(r'<value type="object" struct-name="workbench\.physical\.TableFigure" id="', x):
        nm = re.compile(r'<value type="string" key="name">([^<]*)</value>').search(x, m.end())
        spans.append((m.start(), nm.end(), nm.group(1)))
    real = {}
    for s, e, name in spans:
        g = lambda k: float(re.search(r'key="%s">([-\d.e]+)<' % k, x[s:e]).group(1))
        real[name] = (g('width'), g('height'))
    pos, rx, ry = scaled(box, real)

    out, changed = x, 0
    for s, e, name in sorted(spans, reverse=True):
        if name in pos:
            blk = re.sub(r'(key="left">)[-\d.e]+(<)', r'\g<1>%d\g<2>' % pos[name][0], out[s:e], count=1)
            blk = re.sub(r'(key="top">)[-\d.e]+(<)', r'\g<1>%d\g<2>' % pos[name][1], blk, count=1)
            out = out[:s] + blk + out[e:]
            changed += 1
    # drawSplit sur les connexions dont la FK reference une table hub
    nsplit = 0
    def conn_sub(m):
        nonlocal nsplit
        blk = m.group(0)
        fk = re.search(r'key="foreignKey">(\{[^}]+\})<', blk)
        if fk and fkref.get(fk.group(1), (None, None))[1] in hubs and fkref[fk.group(1)][0] != fkref[fk.group(1)][1]:
            nsplit += 1
            return re.sub(r'(key="drawSplit">)\d(<)', r'\g<1>1\g<2>', blk, count=1)
        return blk
    out = re.sub(r'<value type="object" struct-name="workbench\.physical\.Connection".*?key="startFigure">\{[^}]+\}</link>', conn_sub, out, flags=re.S)

    # chevauchements avec les tailles reelles de Workbench
    rect = {n: (pos[n][0], pos[n][1], real[n][0], real[n][1]) for n in real if n in pos}
    over = [(a, b) for i, a in enumerate(rect) for b in list(rect)[i + 1:]
            if rect[a][0] < rect[b][0] + rect[b][2] and rect[b][0] < rect[a][0] + rect[a][2]
            and rect[a][1] < rect[b][1] + rect[b][3] and rect[b][1] < rect[a][1] + rect[a][3]]
    if over:
        sys.exit('ECHEC : chevauchements avec les tailles Workbench : %s' % over)

    # taille du diagramme et de son calque racine : agrandies si les tables depassent
    need = {'width': max(r[0] + r[2] for r in rect.values()) + MARGIN, 'height': max(r[1] + r[3] for r in rect.values()) + MARGIN}
    edits = [(s, e, v, need[k]) for st in ('workbench.physical.Diagram', 'workbench.physical.Layer') for k in need
             for s, e, v in own_value(out, st, k)]
    for s, e, v, n in sorted(edits, reverse=True):
        if v < n:
            out = out[:s] + '%g' % n + out[e:]

    import xml.dom.minidom
    xml.dom.minidom.parseString(out.encode('utf-8'))
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        zout.writestr(doc_info, out.encode('utf-8'))
        for it, data in others:
            zout.writestr(it, data)
    assert hashlib.sha256(open(src, 'rb').read()).hexdigest() == h0, 'la source a change !'
    absent = sorted(set(pos) - set(real))
    print(f'mwb : {dst} ({changed} tables placees, echelle x{rx:.3f} y{ry:.3f} sur les tailles Workbench, {nsplit} liens en split, '
          f'0 chevauchement{", absentes du modele : " + ", ".join(absent) if absent else ""}) ; source inchangee (sha256 {h0[:12]})')


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'script':
        cmd_script(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 5 and sys.argv[1] == 'patch':
        cmd_patch(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        sys.exit(__doc__)
