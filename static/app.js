const state = {
  selectedFile: null,
  lastSvg: '',
  lastText: '',
  styles: [],
};

const $ = (id) => document.getElementById(id);

document.querySelectorAll('.tab').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    button.classList.add('active');
    $("tab-" + button.dataset.tab).classList.add('active');
  });
});

async function fetchHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    $('healthPill').textContent = data.status === 'ok' ? 'local OK' : data.status;
  } catch {
    $('healthPill').textContent = 'offline';
  }
}

async function loadStyles() {
  const res = await fetch('/styles');
  const data = await res.json();
  state.styles = data.styles || [];

  const select = $('styleSelect');
  const list = $('stylesList');
  select.innerHTML = '';
  list.innerHTML = '';

  state.styles.forEach((style) => {
    const option = document.createElement('option');
    option.value = style.name;
    option.textContent = style.name;
    select.appendChild(option);

    const card = document.createElement('div');
    card.className = 'style-card';
    card.innerHTML = `
      <strong>${escapeHtml(style.name)}</strong>
      <span>slant ${Number(style.slant_degrees ?? 0).toFixed(1)}° · width ${Number(style.stroke_width ?? 0).toFixed(1)} · scale ${Number(style.size_scale ?? 1).toFixed(1)}</span>
      <small>${escapeHtml(style.sample_text || 'No note')}</small>
    `;
    list.appendChild(card);
  });

  updateStyleInfo();
}

function updateStyleInfo() {
  const selected = $('styleSelect').value;
  const style = state.styles.find((x) => x.name === selected);
  $('styleInfo').textContent = style ? `${style.name}: bias ${style.seed_bias}, jitter ${style.baseline_jitter}` : 'No style selected';
}

$('styleSelect').addEventListener('change', updateStyleInfo);

const dropzone = $('dropzone');
const ocrFile = $('ocrFile');

dropzone.addEventListener('click', () => ocrFile.click());
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  const file = e.dataTransfer.files?.[0];
  if (file) setFile(file);
});
ocrFile.addEventListener('change', () => {
  const file = ocrFile.files?.[0];
  if (file) setFile(file);
});

function setFile(file) {
  state.selectedFile = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    $('previewImage').src = e.target.result;
    $('previewWrap').classList.remove('hidden');
  };
  reader.readAsDataURL(file);
  $('ocrProgress').textContent = `${file.name} selected`;
}

$('clearPreviewBtn').addEventListener('click', () => {
  state.selectedFile = null;
  $('previewWrap').classList.add('hidden');
  $('previewImage').src = '';
  $('ocrOutput').value = '';
  $('ocrResult').classList.add('hidden');
  $('ocrProgress').textContent = 'Idle';
  ocrFile.value = '';
});

$('ocrBtn').addEventListener('click', async () => {
  if (!state.selectedFile) {
    $('ocrProgress').textContent = 'Choose an image first';
    return;
  }
  $('ocrBtn').disabled = true;
  $('ocrProgress').textContent = 'Loading model / transcribing… this can take a while on CPU';
  try {
    const form = new FormData();
    form.append('file', state.selectedFile);
    const res = await fetch('/ocr', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'OCR failed');

    $('ocrOutput').value = data.text || '';
    $('ocrMeta').textContent = `model: ${data.model || 'unknown'} · confidence: ${data.confidence ?? 'n/a'}`;
    $('ocrResult').classList.remove('hidden');
    $('ocrProgress').textContent = 'Done';
  } catch (err) {
    $('ocrProgress').textContent = err.message;
  } finally {
    $('ocrBtn').disabled = false;
  }
});

$('copyOcrBtn').addEventListener('click', async () => {
  await navigator.clipboard.writeText($('ocrOutput').value || '');
  $('copyOcrBtn').textContent = 'Copied';
  setTimeout(() => $('copyOcrBtn').textContent = 'Copy', 1200);
});

$('genBtn').addEventListener('click', generateSvg);
$('regenBtn').addEventListener('click', generateSvg);

async function generateSvg() {
  const text = $('genInput').value.trim();
  if (!text) {
    $('genProgress').textContent = 'Enter some text';
    return;
  }

  $('genBtn').disabled = true;
  $('regenBtn').disabled = true;
  $('genProgress').textContent = 'Generating fresh sample…';
  try {
    const payload = { text, style: $('styleSelect').value || 'default' };
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Generation failed');

    state.lastSvg = data.svg;
    state.lastText = text;
    $('svgStage').innerHTML = data.svg;
    $('genResult').classList.remove('hidden');
    $('genProgress').textContent = `Done with ${data.engine}`;
  } catch (err) {
    $('genProgress').textContent = err.message;
  } finally {
    $('genBtn').disabled = false;
    $('regenBtn').disabled = false;
  }
}

$('downloadSvgBtn').addEventListener('click', () => {
  if (!state.lastSvg) return;
  const blob = new Blob([state.lastSvg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'handwriting.svg';
  a.click();
  URL.revokeObjectURL(url);
});

$('downloadPngBtn').addEventListener('click', () => {
  if (!state.lastSvg) return;
  const blob = new Blob([state.lastSvg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    const svg = $('svgStage').querySelector('svg');
    const width = svg?.viewBox?.baseVal?.width || 1200;
    const height = svg?.viewBox?.baseVal?.height || 260;
    const canvas = document.createElement('canvas');
    canvas.width = width * 2;
    canvas.height = height * 2;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#0d0d0d';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const pngUrl = canvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = pngUrl;
    a.download = 'handwriting.png';
    a.click();
    URL.revokeObjectURL(url);
  };
  img.src = url;
});

$('buildStyleBtn').addEventListener('click', async () => {
  const file = $('styleImage').files?.[0];
  const styleName = $('styleName').value.trim();
  const sampleText = $('sampleText').value.trim();
  if (!styleName) {
    $('styleImageProgress').textContent = 'Style name is required';
    return;
  }
  if (!file) {
    $('styleImageProgress').textContent = 'Choose a handwriting image';
    return;
  }

  $('buildStyleBtn').disabled = true;
  $('styleImageProgress').textContent = 'Extracting style from image…';
  try {
    const form = new FormData();
    form.append('style_name', styleName);
    form.append('sample_text', sampleText);
    form.append('file', file);
    const res = await fetch('/styles/from-image', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not build style from image');
    $('styleImageProgress').textContent = `Saved ${data.style.name} from image`;
    await loadStyles();
    $('styleSelect').value = data.style.name;
    updateStyleInfo();
  } catch (err) {
    $('styleImageProgress').textContent = err.message;
  } finally {
    $('buildStyleBtn').disabled = false;
  }
});

$('saveStyleBtn').addEventListener('click', async () => {
  const payload = {
    style_name: $('styleName').value.trim(),
    sample_text: $('sampleText').value.trim(),
    slant_degrees: parseFloat($('slant').value || '-6'),
    stroke_width: parseFloat($('strokeWidth').value || '2.2'),
    letter_spacing: parseFloat($('letterSpacing').value || '0'),
    word_spacing: parseFloat($('wordSpacing').value || '16'),
    baseline_jitter: parseFloat($('baselineJitter').value || '2'),
    pressure_variance: parseFloat($('pressureVariance').value || '0.3'),
    size_scale: parseFloat($('sizeScale').value || '1'),
    seed_bias: parseFloat($('seedBias').value || '0.5'),
  };

  if (!payload.style_name) {
    $('styleProgress').textContent = 'Style name is required';
    return;
  }

  $('saveStyleBtn').disabled = true;
  $('styleProgress').textContent = 'Saving…';
  try {
    const res = await fetch('/styles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not save style');
    $('styleProgress').textContent = `Saved ${data.style.name}`;
    await loadStyles();
    $('styleSelect').value = data.style.name;
    updateStyleInfo();
  } catch (err) {
    $('styleProgress').textContent = err.message;
  } finally {
    $('saveStyleBtn').disabled = false;
  }
});

function escapeHtml(str) {
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function loadPresetGallery() {
  const res = await fetch('/style-previews');
  const data = await res.json();
  const root = $('presetGallery');
  root.innerHTML = '';

  (data.previews || []).forEach((item) => {
    const card = document.createElement('div');
    card.className = 'gallery-card';
    if (item.error) {
      card.innerHTML = `<strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.sample_text || '')}</small><div class="inline-note">${escapeHtml(item.error)}</div>`;
    } else {
      card.innerHTML = `
        <div class="gallery-top">
          <div>
            <strong>${escapeHtml(item.name)}</strong>
            <small>${escapeHtml(item.sample_text || '')}</small>
          </div>
          <button class="ghost choose-style-btn" data-style="${escapeHtml(item.name)}">Use this</button>
        </div>
        <div class="gallery-preview">${item.svg}</div>
      `;
    }
    root.appendChild(card);
  });

  root.querySelectorAll('.choose-style-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      $('styleSelect').value = btn.dataset.style;
      updateStyleInfo();
      document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
      document.querySelector('.tab[data-tab="write"]').classList.add('active');
      $('tab-write').classList.add('active');
    });
  });
}

fetchHealth();
loadStyles();
loadPresetGallery();
