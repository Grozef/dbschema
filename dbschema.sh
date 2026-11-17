#!/usr/bin/env bash
# dbschema : schema de BDD relationnelle -> HTML interactif + PNG + SQL (+ mise en page Workbench).
# Usage :
#   dbschema.sh all  (--sql F | --laravel DIR | --db NOM) --out DIR --name NOM [--groups F.json] [--cards F.json] [--frames]
#                    [--hub K|off] [--title "..."] [--mwb MODELE.mwb]
#   dbschema.sh test [DIR_TMP]          suite de tests du skill (cas limites + schema de demonstration)
# Ecritures BDD : uniquement dans des bases jetables zz_dbschema_* (supprimees en fin d'extraction, meme en erreur).
# Workbench n'est jamais lance (mono-instance : un --run-script part dans la session ouverte de l'utilisateur).
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=(python -I)
die() { echo "dbschema: $*" >&2; exit 2; }

cmd="${1:-}"; shift || true
case "$cmd" in
  test)
    tmp="${1:-$(mktemp -d)}"
    exec "${PY[@]}" "$SKILL/tests/run_tests.py" "$tmp" ;;
  all) ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac

src=() out="" name="" groups="" cards="" frames="" hub="" title="" mwb="" trust=""
while [ $# -gt 0 ]; do
  case "$1" in
    --sql|--laravel|--db) src=("$1" "$2"); shift 2 ;;
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

echo "== extraction"
"${PY[@]}" "$SKILL/lib/extract.py" "${src[@]}" --out "$out/_build/model.json" --sql-out "$out/$name.sql" ${groups:+--groups "$groups"} ${cards:+--cards "$cards"} ${trust:+"$trust"}

echo "== mise en page, controles, rendus"
node "$SKILL/lib/build.mjs" "$out/_build/model.json" "$out" "$name" ${frames:+"$frames"} ${hub:+"$hub"} --title="${title:-$name}"

echo "== Workbench"
"${PY[@]}" "$SKILL/lib/workbench.py" script "$out/_build/layout_all.json" "$out/${name}_workbench_layout.py"
if [ -n "$mwb" ]; then
  "${PY[@]}" "$SKILL/lib/workbench.py" patch "$out/_build/layout_all.json" "$mwb" "$out/${name}_layout.mwb"
fi
echo "== livrables"
ls -la "$out" | grep -v "_build"
echo "RAPPEL : LIRE $out/$name.png (outil Read) avant d'annoncer quoi que ce soit."
