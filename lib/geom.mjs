// Geometrie et formats partages par layout.mjs (place), check.mjs (controle) et svg.mjs (dessine) : une seule source,
// sinon le controle peut valider une geometrie que le rendu ne dessine plus.
export const HEAD = 26, ROW = 22, FOOT = 26; // en-tete, ligne de colonne, pied (Indexes) d'une carte
export const STUB = 16; // longueur d'une amorce de lien hub
export const TYPE_MAX = 40; // type affiche tronque au-dela (ENUM longs) : type complet dans le panneau de detail du HTML

export const shortType = (c) => {
  const t = [...c.type.toUpperCase().replace(/ UNSIGNED/, '')]; // par caracteres : un emoji n'est jamais coupe en deux
  return t.length > TYPE_MAX ? t.slice(0, TYPE_MAX - 1).join('') + '…' : t.join('');
};

export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
