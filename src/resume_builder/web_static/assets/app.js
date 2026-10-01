'use strict';

const tabs = document.querySelectorAll('.tab');
const yamlInput = document.getElementById('yamlInput');
const lineNumbersEl = document.getElementById('lineNumbers');
const statusEl = document.getElementById('status');
const downloadBtn = document.getElementById('downloadBtn');
const loadExampleBtn = document.getElementById('loadExampleBtn');
const photoLabel = document.getElementById('photoLabel');
const photoInput = document.getElementById('photoInput');
const removePhotoBtn = document.getElementById('removePhotoBtn');
const pdfFrame = document.getElementById('pdfFrame');
const pdfPlaceholder = document.getElementById('pdfPlaceholder');
const pdfOverlay = document.getElementById('pdfOverlay');

let kind = 'resume';
let currentBlobUrl = null;
let debounceTimer = null;
let requestSeq = 0;
let templateSeq = 0;

// Photo lives entirely in JS memory, never written into the YAML textarea.
// It's merged into the payload only at render/submit time — this keeps the
// editor readable (no giant base64 blob inline) and keeps every keystroke's
// debounced re-render from re-transmitting the full image on unrelated edits.
let currentPhotoDataUrl = null;

// Keep these at or below the server's limits (8 MB body, 3 MB decoded photo).
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024; // raw file guard, before compression
const MAX_ENCODED_BYTES = 2 * 1024 * 1024; // guard on the compressed data URI
const MAX_PHOTO_DIMENSION = 900; // px, longest side, after downscale
const PHOTO_JPEG_QUALITY = 0.85;

// The starter YAML for each document kind lives next to this file, so there is
// one copy to maintain (the server's tests validate both against the models).
const templateCache = new Map();

async function fetchTemplate(k) {
  if (!templateCache.has(k)) {
    const res = await fetch(`/assets/templates/${k}.yaml`);
    if (!res.ok) throw new Error(`Could not load the ${k} template (${res.status})`);
    templateCache.set(k, await res.text());
  }
  return templateCache.get(k);
}

function endpointFor(k) {
  return k === 'resume' ? '/api/resume/pdf' : '/api/cover-letter/pdf';
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || '';
}

function showOverlay(show) {
  pdfOverlay.hidden = !show;
}

function clearPhoto() {
  currentPhotoDataUrl = null;
  updatePhotoStatus();
}

function updatePhotoStatus() {
  removePhotoBtn.hidden = !currentPhotoDataUrl;
}

function updateLineNumbers() {
  const count = yamlInput.value.split('\n').length;
  let out = '';
  for (let i = 1; i <= count; i++) out += i + '\n';
  lineNumbersEl.textContent = out;
}

async function loadTemplate() {
  const seq = ++templateSeq;
  try {
    const text = await fetchTemplate(kind);
    if (seq !== templateSeq) return; // the user switched tabs meanwhile
    yamlInput.value = text;
    clearPhoto();
    updateLineNumbers();
    scheduleRender(0);
  } catch (e) {
    setStatus(e.message, 'error');
  }
}

function parseYaml(raw) {
  // jsyaml.load throws jsyaml.YAMLException with a readable .message
  // (including the line/column) on malformed YAML.
  return jsyaml.load(raw);
}

// Downscales + re-encodes an image file client-side so a resume headshot
// never ships as an untouched multi-MB phone photo. Always outputs JPEG,
// which compresses far better than PNG for photos.
function compressImage(file, maxDim, quality) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      if (width > maxDim || height > maxDim) {
        const scale = maxDim / Math.max(width, height);
        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(objectUrl);
      resolve(canvas.toDataURL('image/jpeg', quality));
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error('Could not decode that image file'));
    };
    img.src = objectUrl;
  });
}

function selectKind(next) {
  kind = next;
  tabs.forEach((t) => t.setAttribute('aria-pressed', String(t.dataset.kind === next)));
  photoLabel.hidden = kind !== 'resume';
  resetPreview();
  loadTemplate();
}

tabs.forEach((t) => t.addEventListener('click', () => selectKind(t.dataset.kind)));

loadExampleBtn.addEventListener('click', loadTemplate);

removePhotoBtn.addEventListener('click', () => {
  clearPhoto();
  scheduleRender(0);
});

photoInput.addEventListener('change', async () => {
  const file = photoInput.files[0];
  photoInput.value = ''; // allow re-selecting the same file later
  if (!file) return;

  if (file.size > MAX_UPLOAD_BYTES) {
    setStatus(
      `That image is too large (${Math.round(file.size / 1024 / 1024)}MB, max 15MB before compression)`,
      'error',
    );
    return;
  }

  setStatus('Compressing photo…');
  try {
    const dataUrl = await compressImage(file, MAX_PHOTO_DIMENSION, PHOTO_JPEG_QUALITY);
    const base64Len = dataUrl.length - dataUrl.indexOf(',') - 1;
    const approxBytes = Math.round(base64Len * 0.75);

    if (approxBytes > MAX_ENCODED_BYTES) {
      setStatus(
        `Photo is still too large after compression (~${Math.round(approxBytes / 1024)}KB, max ${MAX_ENCODED_BYTES / 1024 / 1024}MB) — try a smaller or simpler image`,
        'error',
      );
      return;
    }

    currentPhotoDataUrl = dataUrl;
    updatePhotoStatus();
    setStatus('');
    scheduleRender(0);
  } catch (e) {
    setStatus(e.message, 'error');
  }
});

function resetPreview() {
  if (currentBlobUrl) {
    URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl = null;
  }
  pdfFrame.hidden = true;
  pdfFrame.removeAttribute('src');
  pdfPlaceholder.hidden = false;
  downloadBtn.disabled = true;
  setStatus('');
}

yamlInput.addEventListener('input', () => {
  updateLineNumbers();
  scheduleRender(700);
});
yamlInput.addEventListener('scroll', () => {
  lineNumbersEl.scrollTop = yamlInput.scrollTop;
});

function scheduleRender(delayMs) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(renderPreview, delayMs);
}

// Turns an error response into one readable status line per problem.
async function describeError(res) {
  const err = await res.json().catch(() => ({}));
  if (Array.isArray(err.detail)) {
    return err.detail
      .map((d) => `${(d.loc || []).filter((p) => p !== 'body').join('.')}: ${d.msg}`)
      .join('\n');
  }
  if (err.detail) {
    return typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
  }
  return `Render failed (${res.status})`;
}

async function renderPreview() {
  const raw = yamlInput.value.trim();
  if (!raw) {
    resetPreview();
    return;
  }

  let payload;
  try {
    payload = parseYaml(raw);
  } catch (e) {
    setStatus('Invalid YAML: ' + e.message, 'error');
    downloadBtn.disabled = true;
    return;
  }
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    setStatus('The YAML must be a mapping of fields (name: value, …)', 'error');
    downloadBtn.disabled = true;
    return;
  }

  // Photo is merged in here, right before sending — it never lives in the
  // YAML text itself, so it doesn't get re-parsed/re-typed by the user
  // and doesn't bloat every debounced request beyond what changed.
  // Also force sections.photo on, since the default template ships with
  // it off (no-photo-by-default) and an uploaded photo should always show.
  if (kind === 'resume' && currentPhotoDataUrl) {
    payload.photo = currentPhotoDataUrl;
    payload.sections = { ...(payload.sections || {}), photo: true };
  }

  const seq = ++requestSeq;
  showOverlay(true);
  setStatus('Rendering…');

  try {
    const res = await fetch(endpointFor(kind), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (seq !== requestSeq) return; // a newer request superseded this one

    if (!res.ok) {
      setStatus(await describeError(res), 'error');
      downloadBtn.disabled = true;
      return;
    }

    const blob = await res.blob();
    if (seq !== requestSeq) return;

    if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl = URL.createObjectURL(blob);
    pdfFrame.src = currentBlobUrl;
    pdfFrame.hidden = false;
    pdfPlaceholder.hidden = true;
    downloadBtn.disabled = false;
    setStatus('Up to date', 'ok');
  } catch (e) {
    if (seq !== requestSeq) return;
    setStatus(e.message, 'error');
    downloadBtn.disabled = true;
  } finally {
    if (seq === requestSeq) showOverlay(false);
  }
}

downloadBtn.addEventListener('click', () => {
  if (!currentBlobUrl) return;
  const a = document.createElement('a');
  a.href = currentBlobUrl;
  a.download = kind === 'resume' ? 'resume.pdf' : 'cover_letter.pdf';
  document.body.appendChild(a);
  a.click();
  a.remove();
});

selectKind('resume');
