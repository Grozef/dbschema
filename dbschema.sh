#!/usr/bin/env bash
# dbschema : schema de BDD relationnelle -> HTML interactif + PNG + SQL (+ mise en page Workbench).
# Usage :
#   dbschema.sh all  (--sql F | --laravel DIR | --db NOM) --out DIR --name NOM [--groups F.json] [--cards F.json] [--frames]
#                    [--hub K|off] [--title "..."] [--mwb MODELE.mwb] [--trust-repo] [--keep-framework]
#   dbschema.sh test [options pytest]   tests du skill : node:test (tests/js) puis pytest (ex. -m unit, -m "not perf")
# Ecritures BDD : uniquement dans des bases jetables zz_dbschema_* (supprimees en fin d'extraction, meme en erreur).
# Workbench n'est jamais lance (mono-instance : un --run-script part dans la session ouverte de l'utilisateur).
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
die() { echo "dbschema: $*" >&2; exit 2; }
# python3 s'il tourne vraiment (sous Windows, python3 est souvent le raccourci du Microsoft Store), sinon python ; 3.9 minimum
PY=()
for p in python3 python; do
  if "$p" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then PY=("$p" -I); break; fi
done
[ ${#PY[@]} -gt 0 ] || die "Python 3.9+ introuvable (python3 ou python)"

cmd="${1:-}"; shift || true
case "$cmd" in
  test)
    # pytest hors -I : il peut etre installe dans le site utilisateur (pip install --user -r requirements-dev.txt)
    "${PY[0]}" -c 'import pytest' 2>/dev/null || die "pytest absent : pip install -r $SKILL/requirements-dev.txt"
    [ -d "$SKILL/node_modules/elkjs" ] || (cd "$SKILL" && npm ci --ignore-scripts --no-audit --no-fund >/dev/null) || die "npm ci a echoue"
    node --test "$SKILL"/tests/js/*.test.mjs || exit 1
    cd "$SKILL" && exec "${PY[0]}" -m pytest "$@" ;;
  all) ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac

src=() out="" name="" groups="" cards="" frames="" hub="" title="" mwb="" trust="" keep=""
while [ $# -gt 0 ]; do
  case "$1" in
    --sql|--laravel|--db) [ ${#src[@]} -eq 0 ] || die "une seule source (${src[0]} deja donnee, puis $1)"; src=("$1" "$2"); shift 2 ;;
    --keep-framework) keep="--keep-framework"; shift ;;
    --out) out="$2"; shift 2 ;;
    --name) name="$2"; shift 2 ;;
    --groups) groups="$2"; shift 2 ;;
    --cards) cards="$2"; shift 2 ;;
    --frames) frames="--frames"; shift ;;
    --hub) hub="--hub=$2"; shift 2 ;;
    --trust-repo) trust="--trust-repo"; shift ;;
    --title) title="$2"; shift 2 ;;
    --mwb) mwb="$2"; shift 2 ;;
    *) die "option inconnue : $1" ;;
  esac
done
[ ${#src[@]} -eq 2 ] || die "source manquante (--sql | --laravel | --db)"
[[ "$name" =~ ^[A-Za-z0-9._-]+$ && "$name" != .* ]] || die "--name : lettres, chiffres, . _ - seulement (pas de chemin)"
[[ -z "$hub" || "$hub" =~ ^--hub=([0-9]+|off)$ ]] || die "--hub : un nombre ou off"
[ -n "$out" ] && [ -n "$name" ] || die "--out et --name obligatoires"
[ -d "$SKILL/node_modules/elkjs" ] || (cd "$SKILL" && npm ci --ignore-scripts --no-audit --no-fund >/dev/null) || die "npm ci a echoue dans $SKILL"
mkdir -p "$out/_build"
debut="$out/_build/.debut"; : > "$debut"  # repere de date : un livrable plus ancien vient d'une execution precedente

echo "== extraction"
"${PY[@]}" "$SKILL/lib/extract.py" "${src[@]}" --out "$out/_build/model.json" --sql-out "$out/$name.sql" ${groups:+--groups "$groups"} ${cards:+--cards "$cards"} ${trust:+"$trust"} ${keep:+"$keep"}

echo "== mise en page, controles, rendus"
node "$SKILL/lib/build.mjs" "$out/_build/model.json" "$out" "$name" ${frames:+"$frames"} ${hub:+"$hub"} --title="${title:-$name}"

echo "== Workbench"
"${PY[@]}" "$SKILL/lib/workbench.py" script "$out/_build/layout_all.json" "$out/${name}_workbench_layout.py"
if [ -n "$mwb" ]; then
  "${PY[@]}" "$SKILL/lib/workbench.py" patch "$out/_build/layout_all.json" "$mwb" "$out/${name}_layout.mwb"
fi
echo "== livrables"
ls -la "$out" | grep -v "_build"
if [ "$out/$name.png" -nt "$debut" ]; then
  echo "RAPPEL : LIRE $out/$name.png (outil Read) avant d'annoncer quoi que ce soit."
else
  echo "PNG NON PRODUIT par cette execution : $out/$name.png absent ou ancien (ne pas le lire comme le resultat). Verifier le HTML."
fi
