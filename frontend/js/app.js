let map, drawnItems, currentData = null;
const tipos = [
  'Vizinho','Logradouro Público','Área Pública','Área de Preservação Permanente',
  'Faixa de Domínio','Faixa de Servidão','Área Remanescente','Outro'
];

window.addEventListener('load', async () => {
  setupMap();
  await loadCrs();
  bindEvents();
});

function setupMap(){
  map = L.map('map').setView([-23.55, -46.22], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 20, attribution:'© OpenStreetMap'}).addTo(map);
  drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);
  const drawControl = new L.Control.Draw({
    draw: {polyline:false, rectangle:false, circle:false, marker:false, circlemarker:false},
    edit: {featureGroup: drawnItems}
  });
  map.addControl(drawControl);
  map.on(L.Draw.Event.CREATED, async (e) => {
    resetState(false);
    drawnItems.clearLayers();
    drawnItems.addLayer(e.layer);
    const latlngs = e.layer.getLatLngs()[0];
    const coords = latlngs.map(p => [p.lng, p.lat]);
    try{
      const resp = await fetch('/api/process/manual', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({coords, input_crs:'wgs84'})
      });
      handleProcessed(await readJsonOrThrow(resp));
    }catch(err){ alert(err.message); }
  });
}

async function loadCrs(){
  const data = await (await fetch('/api/crs')).json();
  const sel = document.getElementById('inputCrs');
  Object.entries(data).forEach(([key,val]) => {
    const opt = document.createElement('option'); opt.value = key; opt.textContent = val.label; sel.appendChild(opt);
  });
}

function bindEvents(){
  document.getElementById('btnCsv').onclick = () => upload('/api/parse/csv', 'csvFile');
  document.getElementById('btnGeojson').onclick = () => upload('/api/parse/geojson', 'geojsonFile');
  document.getElementById('btnShp').onclick = () => upload('/api/parse/shapefile', 'shpFile');
  document.getElementById('btnReset').onclick = () => resetState(true);
  document.getElementById('okGeom').onchange = e => {
    document.getElementById('frontCard').hidden = !e.target.checked;
    document.getElementById('dadosCard').hidden = !e.target.checked;
  };
  document.getElementById('faceFrente').onchange = applyFrenteRule;
  document.getElementById('btnPrevia').onclick = gerarPrevia;
  document.getElementById('btnEmitir').onclick = emitir;
  document.getElementById('btnRecuperar').onclick = () => document.getElementById('dlgRecuperar').showModal();
  document.getElementById('btnBuscarMemorial').onclick = recuperar;
}

async function readJsonOrThrow(resp){
  const text = await resp.text();
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error(`O servidor devolveu uma resposta inesperada. Status ${resp.status}. Abra o terminal do Flask para ver o erro.`); }
  if(!resp.ok || data.error) throw new Error(data.error || `Erro HTTP ${resp.status}`);
  return data;
}

async function upload(url, inputId){
  const f = document.getElementById(inputId).files[0];
  if(!f){ alert('Selecione um arquivo.'); return; }
  resetState(false);
  const fd = new FormData();
  fd.append('file', f);
  fd.append('input_crs', document.getElementById('inputCrs').value);
  try{
    const data = await readJsonOrThrow(await fetch(url, {method:'POST', body:fd}));
    handleProcessed(data);
  }catch(e){ alert(e.message); }
}

function resetState(clearFiles){
  currentData = null;
  drawnItems.clearLayers();
  ['validationCard','frontCard','dadosCard','previewCard'].forEach(id => document.getElementById(id).hidden = true);
  document.getElementById('validationBox').innerHTML = '';
  document.getElementById('area').textContent = '';
  document.getElementById('perimetro').textContent = '';
  document.getElementById('faceFrente').innerHTML = '';
  document.getElementById('confrontacoes').innerHTML = '';
  document.getElementById('preview').innerHTML = '';
  document.getElementById('resultado').innerHTML = '';
  document.getElementById('okGeom').checked = false;
  document.getElementById('okPreview').checked = false;
  if(clearFiles){
    ['csvFile','geojsonFile','shpFile'].forEach(id => document.getElementById(id).value = '');
  }
}

function handleProcessed(data){
  currentData = data;
  document.getElementById('validationCard').hidden = false;
  const box = document.getElementById('validationBox');
  const cls = data.validation.level === 'green' ? 'ok' : data.validation.level === 'yellow' ? 'warn' : 'err';
  box.className = cls;
  box.innerHTML = data.validation.messages.map(m => `<div>${escapeHtml(m)}</div>`).join('');
  document.getElementById('area').textContent = data.metrics.area_m2;
  document.getElementById('perimetro').textContent = data.metrics.perimetro_m;
  drawProcessedPolygon(data.map_geojson || data.metrics.geojson);
  buildFaces(data.metrics.faces);
  if(data.validation.level === 'red'){
    document.getElementById('okGeom').checked = false;
    document.getElementById('frontCard').hidden = true;
    document.getElementById('dadosCard').hidden = true;
  }
}

function drawProcessedPolygon(geojson){
  drawnItems.clearLayers();
  const coords = geojson.coordinates[0];
  const latlngs = coords.map(([lon,lat]) => [lat,lon]);
  const layer = L.polygon(latlngs, {color:'#1f4e79', weight:3, fillColor:'#7aa6c2', fillOpacity:0.35}).addTo(drawnItems);
  map.fitBounds(layer.getBounds(), {padding:[60,60], maxZoom: 20});

  const verts = currentData.display_vertices || currentData.metrics.vertices.map(v => ({nome:v.nome, lon:v.x, lat:v.y}));
  verts.forEach(v => L.marker([v.lat, v.lon], {title:v.nome}).bindTooltip(v.nome, {permanent:true}).addTo(drawnItems));

  // Linhas clicáveis das faces. Isso ajuda a escolher a frente direto no mapa.
  const open = coords.slice(0, -1);
  open.forEach((pt, i) => {
    const next = open[(i + 1) % open.length];
    const faceId = `V${i+1}-V${((i+1) % open.length)+1}`;
    const faceLine = L.polyline([[pt[1], pt[0]], [next[1], next[0]]], {color:'#0b5c8e', weight:10, opacity:0.01}).addTo(drawnItems);
    faceLine.on('click', () => {
      document.getElementById('faceFrente').value = faceId;
      applyFrenteRule();
      alert(`Face ${faceId} definida como frente/logradouro.`);
    });
  });
}

function buildFaces(faces){
  const frente = document.getElementById('faceFrente');
  frente.innerHTML = faces.map(f => `<option value="${f.id}">${f.id}</option>`).join('');
  const wrap = document.getElementById('confrontacoes');
  wrap.innerHTML = '<h3>Confrontações por face</h3><p class="hint">A face de frente será tratada como Logradouro Público. Informe a descrição de todas as faces.</p>' + faces.map(f => `
    <div class="face-row" data-face="${f.id}">
      <strong>${f.id}</strong>
      <select class="tipo">${tipos.map(t=>`<option>${t}</option>`).join('')}</select>
      <input class="descricao" placeholder="Descrição obrigatória" />
      <input class="outro-tipo" placeholder="Qual tipo?" hidden />
      <small class="front-note" hidden>Frente / Logradouro</small>
    </div>
  `).join('');
  wrap.querySelectorAll('.tipo').forEach(sel => {
    sel.onchange = () => {
      const extra = sel.closest('.face-row').querySelector('.outro-tipo');
      extra.hidden = sel.value !== 'Outro';
    };
  });
  applyFrenteRule();
}

function applyFrenteRule(){
  const frente = document.getElementById('faceFrente').value;
  document.querySelectorAll('.face-row').forEach(row => {
    const isFront = row.dataset.face === frente;
    const sel = row.querySelector('.tipo');
    const desc = row.querySelector('.descricao');
    const note = row.querySelector('.front-note');
    row.classList.toggle('front-row', isFront);
    note.hidden = !isFront;
    if(isFront){
      sel.value = 'Logradouro Público';
      sel.disabled = true;
      desc.placeholder = 'Nome do logradouro obrigatório';
      row.querySelector('.outro-tipo').hidden = true;
    } else {
      sel.disabled = false;
      desc.placeholder = 'Descrição obrigatória';
    }
  });
}

function coletarPayload(){
  if(!currentData) throw new Error('Nenhuma geometria carregada.');
  const dados = {
    proprietario: val('proprietario'), municipio: val('municipio'), quadra: val('quadra'), lote: val('lote'),
    area_declarada: val('areaDeclarada'), matricula: val('matricula'), cartorio: val('cartorio'),
    projeto: val('projeto'), responsavel_tecnico: val('responsavel')
  };
  for(const k of ['proprietario','municipio','quadra','lote']) if(!dados[k]) throw new Error(`Campo obrigatório não preenchido: ${k}`);
  applyFrenteRule();
  const confrontacoes = [...document.querySelectorAll('.face-row')].map(row => ({
    face: row.dataset.face,
    tipo: row.querySelector('.tipo').value,
    tipo_outro: row.querySelector('.outro-tipo').value.trim(),
    descricao: row.querySelector('.descricao').value.trim()
  }));
  for(const c of confrontacoes){
    if(!c.descricao) throw new Error(`Informe a descrição da face ${c.face}.`);
    if(c.tipo === 'Outro' && !c.tipo_outro) throw new Error(`Informe qual é o tipo da face ${c.face}.`);
  }
  if(!confrontacoes.some(c => c.tipo === 'Logradouro Público')){
    throw new Error('Informe pelo menos uma face como Logradouro Público.');
  }
  return {
    ...currentData,
    dados_imovel: dados,
    face_frente: document.getElementById('faceFrente').value,
    confrontacoes
  };
}

function gerarPrevia(){
  try{
    const p = coletarPayload();
    const confRows = p.confrontacoes.map(c=>`<tr><td>${escapeHtml(c.face)}</td><td>${escapeHtml(c.tipo === 'Outro' ? 'Outro - ' + c.tipo_outro : c.tipo)}</td><td>${escapeHtml(c.descricao)}</td></tr>`).join('');
    document.getElementById('previewCard').hidden = false;
    document.getElementById('okPreview').checked = false;
    document.getElementById('preview').innerHTML = `
      <div class="preview-box">
        <h3>Memorial Descritivo</h3>
        <p><b>Proprietário:</b> ${escapeHtml(p.dados_imovel.proprietario)}<br>
        <b>Município:</b> ${escapeHtml(p.dados_imovel.municipio)}<br>
        <b>Quadra:</b> ${escapeHtml(p.dados_imovel.quadra)} | <b>Lote:</b> ${escapeHtml(p.dados_imovel.lote)}<br>
        <b>Área calculada:</b> ${p.metrics.area_m2} m² | <b>Perímetro:</b> ${p.metrics.perimetro_m} m<br>
        <b>Frente:</b> ${escapeHtml(p.face_frente)}</p>
        <table><thead><tr><th>Face</th><th>Tipo</th><th>Descrição</th></tr></thead><tbody>${confRows}</tbody></table>
      </div>`;
  }catch(e){ alert(e.message); }
}

async function emitir(){
  if(!document.getElementById('okPreview').checked){ alert('Confirme a prévia antes de emitir.'); return; }
  try{
    const payload = coletarPayload();
    const resp = await fetch('/api/memorial/emitir', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await readJsonOrThrow(resp);
    document.getElementById('resultado').innerHTML = `<p><b>Protocolo:</b> ${escapeHtml(data.protocolo)}<br><b>Chave:</b> ${escapeHtml(data.chave_validacao)}</p><a href="${data.pdf_url}" target="_blank">Baixar PDF</a>`;
  }catch(e){ alert(e.message); }
}

async function recuperar(){
  const protocolo = val('recProtocolo');
  const chave_validacao = val('recChave');
  try{
    const resp = await fetch('/api/memorial/recuperar', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({protocolo, chave_validacao})});
    const data = await readJsonOrThrow(resp);
    document.getElementById('recResultado').innerHTML = `<p>Memorial localizado.<br>Primeira emissão: ${escapeHtml(data.primeira_emissao)}<br>Total de emissões: ${escapeHtml(String(data.total_emissoes))}</p><a href="${data.pdf_url}" target="_blank">Baixar PDF</a>`;
  }catch(e){ document.getElementById('recResultado').innerHTML = `<p>${escapeHtml(e.message)}</p>`; }
}

function val(id){ return document.getElementById(id).value.trim(); }
function escapeHtml(text){ return String(text).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
