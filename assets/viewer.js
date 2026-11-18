// Interactions de la page HTML de dbschema (zoom, survol, panneau, recherche, vues, theme, export PNG).
// Insere tel quel par lib/render.mjs dans la page ; la CSP de la page autorise ce script par son empreinte sha256.
// Donnees : bloc JSON d'id dbschema-data (tables, relations, groupes, couleurs, file).
const D=JSON.parse(document.getElementById('dbschema-data').textContent); // JSON.parse : un nom "__proto__" reste une cle ordinaire
const main=document.getElementById('main'),stage=document.getElementById('stage'),panel=document.getElementById('panel');
let view=null,svg=null,k=1,tx=0,ty=0,pinned=null,group=null;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function apply(){stage.style.transform='translate('+tx+'px,'+ty+'px) scale('+k+')'}
function fit(){const r=main.getBoundingClientRect(),w=+svg.getAttribute('width'),h=+svg.getAttribute('height');k=Math.min(r.width/w,r.height/h)*0.97;tx=(r.width-w*k)/2;ty=(r.height-h*k)/2;apply()}
// police de remplacement (poste sans Tahoma) : un texte plus large que sa place est comprime a la largeur disponible
function fitText(){if(svg.dataset.fitted)return;svg.dataset.fitted=1;const squeeze=(e,room)=>{if(e.getBBox().width>room){e.setAttribute('textLength',Math.max(10,room));e.setAttribute('lengthAdjust','spacingAndGlyphs')}};
 svg.querySelectorAll('.tbl').forEach(T=>{const c=T.querySelector('.card-bg').getBBox(),tn=T.querySelector('.tn');squeeze(tn,c.x+c.width-6-tn.getBBox().x);
  T.querySelectorAll('.col').forEach(r=>{const n=r.querySelector('.cn'),t=r.querySelector('.ct');squeeze(n,t.getBBox().x-6-n.getBBox().x)})})}
function show(id){
 document.querySelectorAll('.view').forEach(v=>v.hidden=v.dataset.view!==id);
 view=document.querySelector('.view[data-view="'+id+'"]');svg=view.querySelector('svg');bind();fitText();
 if(pinned)focusTable(pinned);else clear();
}
function currentId(){const m=document.getElementById('mode').value,f=document.getElementById('full'),fr=document.getElementById('frames');
 if(m==='all'&&fr&&fr.checked)return 'all-frames';if(m==='all'&&f&&f.checked)return 'all-full';return m}
function clear(){main.classList.remove('focus');svg.querySelectorAll('.on,.nb,.hl').forEach(e=>e.classList.remove('on','nb','hl'))}
function focusTable(t){clear();main.classList.add('focus');const T=svg.querySelector('.tbl[data-table="'+CSS.escape(t)+'"]');if(!T)return;T.classList.add('on');
 svg.querySelectorAll('.rel').forEach(r=>{if(r.dataset.from===t||r.dataset.to===t){r.classList.add('on');for(const n of [r.dataset.from,r.dataset.to]){const N=svg.querySelector('.tbl[data-table="'+CSS.escape(n)+'"]');N&&N.classList.add('nb')}
  const rel=D.relations.find(x=>x.id===r.dataset.rel);if(rel){hlCols(rel.from,rel.columns);hlCols(rel.to,rel.ref_columns)}}})}
function hlCols(t,cols){for(const c of cols){const e=svg.querySelector('.tbl[data-table="'+CSS.escape(t)+'"] .col[data-col="'+CSS.escape(c)+'"]');e&&e.classList.add('hl')}}
function focusGroup(g){clear();main.classList.add('focus');const ts=new Set(D.groups[g]||[]);
 svg.querySelectorAll('.tbl').forEach(T=>{if(ts.has(T.dataset.table))T.classList.add('on')});
 svg.querySelectorAll('.rel').forEach(r=>{if(ts.has(r.dataset.from)&&ts.has(r.dataset.to))r.classList.add('on')})}
function relRow(r,dir){const other=dir==='out'?r.to:r.from;return '<tr><td><a data-go="'+esc(other)+'">'+esc(other)+'</a></td><td>'+esc((dir==='out'?r.columns:r.ref_columns).join(', '))+' &rarr; '+esc((dir==='out'?r.ref_columns:r.columns).join(', '))+'</td><td>'+esc(r.card_parent)+' : '+esc(r.card_child)+'</td></tr>'}
function tablePanel(t){const T=D.tables[t];if(!T)return;const out=D.relations.filter(r=>r.from===t),inn=D.relations.filter(r=>r.to===t);
 panel.innerHTML='<button class="x" title="Fermer">&times;</button><h2>'+esc(t)+'</h2><div>'+esc(T.comment||'')+'</div>'
 +'<h3>Colonnes ('+T.columns.length+')</h3><table><tr><th></th><th>Nom</th><th>Type</th><th>Null</th><th>Défaut</th></tr>'
 +T.columns.map(c=>'<tr title="'+esc(c.comment)+'"><td>'+(c.pk?'PK':'')+(c.fk?' FK':'')+(c.unique?' UQ':'')+'</td><td>'+esc(c.name)+(c.comment?'<br><small>'+esc(c.comment)+'</small>':'')+'</td><td>'+esc(c.type)+'</td><td>'+(c.nullable?'oui':'non')+'</td><td>'+esc(c.default??'')+'</td></tr>').join('')+'</table>'
 +'<h3>Index ('+T.indexes.length+')</h3><table>'+T.indexes.map(i=>'<tr><td>'+esc(i.name)+'</td><td>'+(i.unique?'UNIQUE':'')+'</td><td>'+esc(i.columns.join(', '))+'</td></tr>').join('')+'</table>'
 +'<h3>Référence ('+out.length+')</h3><table>'+out.map(r=>relRow(r,'out')).join('')+'</table>'
 +'<h3>Référencée par ('+inn.length+')</h3><table>'+inn.map(r=>relRow(r,'in')).join('')+'</table>';panel.hidden=false}
function relPanel(id){const r=D.relations.find(x=>x.id===id);if(!r)return;
 panel.innerHTML='<button class="x">&times;</button><h2>'+esc(r.name)+'</h2><table>'
 +'<tr><th>Table</th><td><a data-go="'+esc(r.from)+'">'+esc(r.from)+'</a> ('+esc(r.columns.join(', '))+')</td></tr>'
 +'<tr><th>Référence</th><td><a data-go="'+esc(r.to)+'">'+esc(r.to)+'</a> ('+esc(r.ref_columns.join(', '))+')</td></tr>'
 +'<tr><th>Cardinalité</th><td>'+esc(r.to)+' '+esc(r.card_parent)+' &mdash; '+esc(r.card_child)+' '+esc(r.from)+(r.declared?' <small>(déclarée : '+esc(r.declared.join(', '))+')</small>':' <small>(déduite du schéma)</small>')+'</td></tr>'
 +'<tr><th>ON DELETE</th><td>'+esc(r.on_delete)+'</td></tr><tr><th>ON UPDATE</th><td>'+esc(r.on_update)+'</td></tr></table>';panel.hidden=false}
function centerOn(t){const T=svg.querySelector('.tbl[data-table="'+CSS.escape(t)+'"] .card-bg');if(!T)return;const b=T.getBBox(),r=main.getBoundingClientRect();
 k=Math.max(k,0.8);tx=r.width/2-(b.x+b.width/2)*k;ty=r.height/2-(b.y+b.height/2)*k;apply()}
function go(t){pinned=t;focusTable(t);tablePanel(t);centerOn(t)}
function bind(){if(svg.dataset.bound)return;svg.dataset.bound=1;
 svg.querySelectorAll('.tbl').forEach(T=>{T.addEventListener('mouseenter',()=>{if(!pinned&&!group)focusTable(T.dataset.table)});
  T.addEventListener('mouseleave',()=>{if(!pinned&&!group)clear()});
  T.addEventListener('click',e=>{e.stopPropagation();if(moved)return;pinned=T.dataset.table;group=null;focusTable(pinned);tablePanel(pinned)})});
 svg.querySelectorAll('.rel').forEach(R=>R.addEventListener('click',e=>{e.stopPropagation();if(moved)return;clear();main.classList.add('focus');R.classList.add('on');
  for(const n of [R.dataset.from,R.dataset.to]){const N=svg.querySelector('.tbl[data-table="'+CSS.escape(n)+'"]');N&&N.classList.add('nb')}relPanel(R.dataset.rel)}))}
panel.addEventListener('click',e=>{if(e.target.classList.contains('x')){panel.hidden=true;pinned=null;clear()}const a=e.target.closest('[data-go]');if(a)go(a.dataset.go)});
let drag=null,moved=false;
main.addEventListener('mousedown',e=>{if(e.target.closest('aside'))return;drag={x:e.clientX,y:e.clientY,tx,ty};moved=false;main.classList.add('drag')});
addEventListener('mousemove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;tx=drag.tx+dx;ty=drag.ty+dy;apply()});
addEventListener('mouseup',()=>{drag=null;main.classList.remove('drag');setTimeout(()=>moved=false,0)});
main.addEventListener('click',e=>{if(moved||e.target.closest('aside'))return;if(!e.target.closest('.tbl,.rel')){pinned=null;group=null;clear();panel.hidden=true;document.querySelectorAll('.lg').forEach(b=>b.classList.remove('on'))}});
main.addEventListener('wheel',e=>{if(e.target.closest('aside'))return;e.preventDefault();const r=main.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,f=Math.exp(-e.deltaY*0.0015),nk=Math.min(4,Math.max(0.05,k*f));tx=mx-(mx-tx)*nk/k;ty=my-(my-ty)*nk/k;k=nk;apply()},{passive:false});
document.getElementById('fit').onclick=fit;
document.getElementById('zin').onclick=()=>{k*=1.25;apply()};document.getElementById('zout').onclick=()=>{k/=1.25;apply()};
document.getElementById('mode').onchange=()=>{show(currentId());fit()};
for(const id of ['full','frames']){const el=document.getElementById(id);if(el)el.onchange=()=>{if(el.checked)for(const o of ['full','frames'])if(o!==id&&document.getElementById(o))document.getElementById(o).checked=false;show(currentId());fit()}}
document.getElementById('theme').onclick=()=>{const r=document.documentElement;r.dataset.theme=r.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('dbschema-theme',r.dataset.theme)}catch(e){}};
try{const t=localStorage.getItem('dbschema-theme');if(t)document.documentElement.dataset.theme=t;else if(matchMedia('(prefers-color-scheme: dark)').matches)document.documentElement.dataset.theme='dark'}catch(e){}
document.querySelectorAll('.lg').forEach(b=>b.onclick=()=>{const g=b.dataset.group;document.querySelectorAll('.lg').forEach(x=>x.classList.toggle('on',x===b&&group!==g));group=group===g?null:g;pinned=null;panel.hidden=true;group?focusGroup(group):clear()});
const q=document.getElementById('q');
q.addEventListener('input',()=>{const s=q.value.trim().toLowerCase();svg.querySelectorAll('.tbl').forEach(T=>{const t=T.dataset.table,cols=D.tables[t].columns.map(c=>c.name);T.classList.toggle('match',!!s&&(t.toLowerCase().includes(s)||cols.some(c=>c.toLowerCase().includes(s))))})});
q.addEventListener('keydown',e=>{if(e.key!=='Enter')return;const s=q.value.trim().toLowerCase();const t=Object.keys(D.tables).find(t=>t.toLowerCase()===s)||Object.keys(D.tables).find(t=>t.toLowerCase().includes(s))||Object.keys(D.tables).find(t=>D.tables[t].columns.some(c=>c.name.toLowerCase().includes(s)));if(t)go(t)});
addEventListener('keydown',e=>{if(e.key==='Escape'){pinned=null;group=null;clear();panel.hidden=true;document.querySelectorAll('.lg').forEach(b=>b.classList.remove('on'))}});
document.getElementById('png').onclick=()=>{const dark=document.documentElement.dataset.theme==='dark';
 // le SVG exporte est isole (pas de :root[data-theme]) : les regles du theme sombre y sont recopiees sans ce prefixe
 const css=[...document.styleSheets].flatMap(s=>[...s.cssRules].map(r=>r.cssText)).filter(t=>t.includes('.erd')).filter(t=>dark||!t.includes('data-theme')).map(t=>t.replace(/:root\[data-theme="?dark"?\]\s*/g,'')).join('\n');
 const c=svg.cloneNode(true);const st=document.createElementNS('http://www.w3.org/2000/svg','style');st.textContent=css;c.insertBefore(st,c.firstChild);
 if(document.documentElement.dataset.theme==='dark'){c.setAttribute('style','--bg:#16181d;--ink:#e6e8ec;--mute:#98a1b0;--line:#9aa4b2;--bd:#4a5668;--row:#22262d;--foot:#2a2f37')}
 const w=+svg.getAttribute('width'),h=+svg.getAttribute('height'),img=new Image(),url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(c)],{type:'image/svg+xml'}));
 img.onload=()=>{const cv=document.createElement('canvas');cv.width=w*2;cv.height=h*2;const g=cv.getContext('2d');g.scale(2,2);g.drawImage(img,0,0);URL.revokeObjectURL(url);
  cv.toBlob(b=>{const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=D.file+'_'+currentId()+'.png';a.click()})};img.src=url};
// redimensionnement : le point au centre de la vue reste au centre, le zoom est conserve
let vw=main.clientWidth,vh=main.clientHeight;
addEventListener('resize',()=>{tx+=(main.clientWidth-vw)/2;ty+=(main.clientHeight-vh)/2;vw=main.clientWidth;vh=main.clientHeight;apply()});
show(currentId());fit();
