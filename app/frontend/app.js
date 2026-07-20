// «Машина времени: Сахалин» — киоск-флоу (прототип)
const state = { location: null, locationTitle: null, outfit: 'male', variants: [], chosen: null, card: null };
let stream = null, idleTimer = null;

const $ = (s) => document.querySelector(s);
const screens = document.querySelectorAll('.screen');

function show(name) {
  screens.forEach(s => s.classList.toggle('active', s.dataset.screen === name));
  resetIdle();
  if (name === 'capture') startCamera(); else stopCamera();
  if (name === 'welcome') resetState();
}

function resetState() {
  state.location = state.chosen = state.card = null; state.variants = [];
}

// авто-сброс к началу по бездействию (кроме экранов загрузки/готово)
function resetIdle() {
  clearTimeout(idleTimer);
  const cur = document.querySelector('.screen.active')?.dataset.screen;
  if (['welcome', 'loading', 'done'].includes(cur)) return;
  idleTimer = setTimeout(() => show('welcome'), 90000); // 90 c
}
['click', 'touchstart'].forEach(e => document.addEventListener(e, resetIdle));

// навигация по data-go
document.querySelectorAll('[data-go]').forEach(b =>
  b.addEventListener('click', () => show(b.dataset.go)));

// ---------- Локации ----------
async function loadLocations() {
  const r = await fetch('/api/locations');
  const list = await r.json();
  const box = $('#locations'); box.innerHTML = '';
  list.forEach(loc => {
    const el = document.createElement('div');
    el.className = 'loc ' + (loc.enabled ? 'on' : 'off');
    el.innerHTML = `<h3>${loc.title}</h3><p>${loc.subtitle}</p>` +
      (loc.enabled ? '' : '<div class="soon">Скоро</div>');
    if (loc.enabled) el.addEventListener('click', () => {
      state.location = loc.id; state.locationTitle = loc.title;
      $('#capture-title').textContent = `${loc.title}: сделайте фото`;
      show('outfit');
    });
    box.appendChild(el);
  });
}

// выбор образа (одежды)
document.querySelectorAll('.outfit').forEach(o =>
  o.addEventListener('click', () => { state.outfit = o.dataset.outfit; show('capture'); }));

// ---------- Камера ----------
async function startCamera() {
  $('#cam-error').classList.add('hidden');
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 2560 }, height: { ideal: 1920 } },
      audio: false
    });
    $('#video').srcObject = stream;
  } catch (e) {
    $('#cam-error').classList.remove('hidden');
  }
}
function stopCamera() {
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
}

$('#shoot').addEventListener('click', () => {
  const v = $('#video');
  if (!v.videoWidth) return;
  const c = document.createElement('canvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  c.toBlob(b => generate(b), 'image/jpeg', 0.92);
});

$('#file').addEventListener('change', e => {
  if (e.target.files[0]) generate(e.target.files[0]);
});

// ---------- Генерация ----------
async function generate(blob) {
  show('loading');
  const fd = new FormData();
  fd.append('location', state.location);
  fd.append('outfit', state.outfit || 'male');
  fd.append('photo', blob, 'guest.jpg');
  try {
    const r = await fetch('/api/generate', { method: 'POST', body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка генерации');
    const data = await r.json();
    state.variants = data.variants;
    $('#variants-loc').textContent = data.location + (data.stub_mode ? ' · демо-режим (без API-ключа)' : '');
    renderVariants();
    show('variants');
  } catch (e) {
    alert('Не получилось сгенерировать: ' + e.message);
    show('capture');
  }
}

function renderVariants() {
  const box = $('#variants'); box.innerHTML = '';
  state.variants.forEach(v => {
    const img = document.createElement('img');
    img.src = v.url;
    img.addEventListener('click', () => chooseVariant(v, img));
    box.appendChild(img);
  });
}

async function chooseVariant(v, imgEl) {
  document.querySelectorAll('.variants img').forEach(i => i.classList.remove('sel'));
  imgEl.classList.add('sel');
  state.chosen = v.id;
  show('loading');
  $('#loading-note').textContent = 'Собираем фото-карточку с логотипами партнёров…';
  const fd = new FormData(); fd.append('variant_id', v.id);
  try {
    const r = await fetch('/api/card', { method: 'POST', body: fd });
    const data = await r.json();
    state.card = data.card_id;
    $('#card-img').src = data.card_url;
    $('#qr-img').src = data.qr_url;
    show('card');
  } catch (e) {
    alert('Ошибка сборки карточки'); show('variants');
  } finally {
    $('#loading-note').textContent = 'Нейросеть создаёт кадры — это займёт 1–2 минуты. Пожалуйста, подождите и не закрывайте страницу.';
  }
}

$('#retake').addEventListener('click', () => show('capture'));

// ---------- Печать ----------
$('#print').addEventListener('click', async () => {
  const fd = new FormData(); fd.append('card_id', state.card);
  try {
    const r = await fetch('/api/print', { method: 'POST', body: fd });
    const data = await r.json();
    $('#done-note').textContent = data.printed
      ? 'Заберите карточку у стенда' : 'Печать выключена в настройках — карточка сохранена';
    finishFlow();
  } catch (e) { alert('Ошибка печати'); }
});
$('#finish').addEventListener('click', finishFlow);

function finishFlow() {
  show('done');
  let n = 8; $('#cd').textContent = n;
  const t = setInterval(() => {
    n--; $('#cd').textContent = n;
    if (n <= 0) { clearInterval(t); show('welcome'); }
  }, 1000);
}

// init
loadLocations();
