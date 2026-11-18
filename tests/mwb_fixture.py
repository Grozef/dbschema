"""Modele MySQL Workbench (.mwb) synthetique, reduit a ce que lib/workbench.py lit : tables, FK, figures, connexions, calque.
Structure et indentation calquees sur un document.mwb.xml reel (membres indentes de 2 sous leur objet)."""
import zipfile

ROW, HEAD = 22, 52  # hauteur Workbench : 52 + 22 x colonnes


def _fig(i, name, h, layer_id):
    return (f'        <value type="object" struct-name="workbench.physical.TableFigure" id="{{F{i}}}">\n'
            f'          <value type="real" key="height">{h}</value>\n'
            f'          <link type="object" struct-name="model.Layer" key="layer">{layer_id}</link>\n'
            f'          <value type="real" key="left">0</value>\n'
            f'          <link type="object" struct-name="db.Table" key="table">{{T{i}}}</link>\n'
            f'          <value type="real" key="top">0</value>\n'
            f'          <value type="real" key="width">180</value>\n'
            f'          <value type="string" key="name">{name}</value>\n'
            f'        </value>\n')


def xml(tables, fks, layers=1):
    idx = {t: i for i, t in enumerate(tables)}
    out = ['<?xml version="1.0"?>\n<data grt_format="2.0" document_type="MySQL Workbench Model" version="1.4.4">\n',
           '  <value type="object" struct-name="workbench.Document" id="{DOC}">\n',
           '    <value type="object" struct-name="workbench.physical.Diagram" id="{DIAG}">\n',
           '      <value type="real" key="height">200</value>\n      <value type="real" key="width">200</value>\n']
    for k in range(layers):
        out.append(f'      <value type="object" struct-name="workbench.physical.Layer" id="{{L{k}}}">\n'
                   f'        <value type="real" key="height">200</value>\n        <value type="real" key="width">200</value>\n'
                   f'      </value>\n')
    out.append('      <value type="list" content-type="object" key="figures">\n')
    for t, i in idx.items():
        out.append(_fig(i, t, HEAD + ROW * 3, '{L0}'))
    out.append('      </value>\n      <value type="list" content-type="object" key="connections">\n')
    for k, (a, b) in enumerate(fks):
        out.append(f'        <value type="object" struct-name="workbench.physical.Connection" id="{{C{k}}}">\n'
                   f'          <value type="int" key="drawSplit">0</value>\n'
                   f'          <link type="object" struct-name="db.mysql.ForeignKey" key="foreignKey">{{K{k}}}</link>\n'
                   f'          <link type="object" struct-name="model.Figure" key="startFigure">{{F{idx[a]}}}</link>\n'
                   f'        </value>\n')
    out.append('      </value>\n    </value>\n    <value type="list" content-type="object" key="tables">\n')
    for t, i in idx.items():
        out.append(f'      <value type="object" struct-name="db.mysql.Table" id="{{T{i}}}">\n'
                   f'        <value type="string" key="name">{t}</value>\n'
                   f'        <value type="list" content-type="object" key="columns">\n'
                   f'          <value type="object" struct-name="db.mysql.Column" id="{{X{i}}}">\n'
                   f'            <value type="string" key="name">id</value>\n'
                   f'          </value>\n        </value>\n      </value>\n')
    for k, (a, b) in enumerate(fks):
        out.append(f'      <value type="object" struct-name="db.mysql.ForeignKey" id="{{K{k}}}">\n'
                   f'        <link type="object" struct-name="db.mysql.Table" key="owner">{{T{idx[a]}}}</link>\n'
                   f'        <link type="object" struct-name="db.mysql.Table" key="referencedTable">{{T{idx[b]}}}</link>\n'
                   f'      </value>\n')
    out.append('    </value>\n  </value>\n</data>\n')
    return ''.join(out)


def write_mwb(path, tables, fks, layers=1):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('document.mwb.xml', xml(tables, fks, layers))
        z.writestr('lock', b'')
