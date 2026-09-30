// frontend/app.js
const state = {
  documentId: null,
  filename: '',
  pageCount: 0,
  pageNumber: 1,
  pageItems: [],
  pageText: '',
  model: 'jev',     // 'jev' (TypeSafe, needs API key) or 'atom' (public ATOM endpoint)
  threshold: 0.9,
  scale: 2,
  showBoxes: true,
  previewMode: 'width',
  zoom: 1,
  pageResults: {},   // { [pageNumber]: {answers, usage, model, eval_seconds, render_seconds?} }
  batchSummary: null,
  evaluating: false,
  loadToken: 0,      // guards against stale async responses landing on the wrong page
};

const qs = (id) => document.getElementById(id);
const apiBase = (window.JEV_API_BASE_URL || '').replace(/\/$/, '');
const apiFetch = (path, options) => fetch(`${apiBase}${path}`, options);

function parseQuestions(raw) {
  return raw.replace(/<>/g, '\n').split('\n').map((q) => q.trim()).filter(Boolean);
}

function formatQuestionsForDisplay(raw) {
  return raw.replace(/<>/g, '\n').split('\n').map((q) => q.trim()).filter(Boolean).join('\n');
}

function setUploadStatus(message, isError) {
  const el = qs('upload-status');
  el.textContent = message || '';
  el.classList.toggle('error-text', Boolean(isError));
}

async function loadSamples() {
  const response = await apiFetch('/api/samples');
  const body = await response.json();
  const list = qs('sample-list');
  list.innerHTML = '';
  if (!body.samples.length) {
    list.innerHTML = '<p class="text-light">No sample PDFs are available.</p>';
    return;
  }
  for (const name of body.samples) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'outline';
    button.textContent = name;
    button.addEventListener('click', () => uploadSample(name));
    list.appendChild(button);
  }
}

function resetToEmptyState() {
  state.documentId = null;
  state.filename = '';
  state.pageCount = 0;
  state.pageNumber = 1;
  state.pageResults = {};
  state.batchSummary = null;
  qs('empty-state').hidden = false;
  qs('grid').hidden = true;
  qs('document-selected').hidden = true;
  qs('source-tabs').hidden = false;
  qs('file-input').value = '';
  setUploadStatus('', false);
  updateEvaluateButtonState();
}

async function uploadFile(file) {
  setUploadStatus('Extracting text…', false);
  const formData = new FormData();
  formData.append('file', file);
  try {
    const response = await apiFetch('/api/documents', { method: 'POST', body: formData });
    await handleUploadResponse(response, file.name);
  } catch (error) {
    setUploadStatus('Could not reach the server. Check your connection and try again.', true);
  }
}

async function uploadSample(name) {
  setUploadStatus('Extracting text…', false);
  try {
    const response = await apiFetch('/api/documents/from-sample', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    });
    await handleUploadResponse(response, name);
  } catch (error) {
    setUploadStatus('Could not reach the server. Check your connection and try again.', true);
  }
}

async function handleUploadResponse(response, filename) {
  const body = await response.json();
  if (!response.ok) {
    setUploadStatus(body.detail || 'Could not read this PDF.', true);
    return;
  }
  setUploadStatus('', false);
  onDocumentLoaded({ ...body, filename });
}

function onDocumentLoaded({ document_id, page_count, filename }) {
  state.documentId = document_id;
  state.filename = filename;
  state.pageCount = page_count;
  state.pageNumber = 1;
  state.pageResults = {};
  state.batchSummary = null;
  qs('empty-state').hidden = true;
  qs('grid').hidden = false;
  qs('batch-summary').hidden = true;
  qs('doc-filename-label').textContent = filename;
  qs('doc-page-count-label').textContent = `${page_count} page${page_count === 1 ? '' : 's'}`;
  qs('document-selected').hidden = false;
  qs('source-tabs').hidden = true;
  loadPage(1);
}

qs('file-input').addEventListener('change', (event) => {
  const file = event.target.files[0];
  if (file) uploadFile(file);
});
qs('replace-pdf').addEventListener('click', () => resetToEmptyState());

qs('threshold').addEventListener('input', (event) => {
  if (event.target.checkValidity()) state.threshold = event.target.valueAsNumber;
});
qs('threshold').addEventListener('change', (event) => {
  if (event.target.reportValidity() && state.documentId) renderPreview();
});

qs('show-boxes').addEventListener('change', (event) => {
  state.showBoxes = event.target.checked;
  if (state.documentId) renderPreview();
});

qs('toggle-api-key').addEventListener('click', () => {
  const input = qs('api-key');
  const pressed = input.type === 'text';
  input.type = pressed ? 'password' : 'text';
  qs('toggle-api-key').title = pressed ? 'Show API key' : 'Hide API key';
  qs('toggle-api-key').setAttribute('aria-pressed', String(!pressed));
  qs('toggle-api-key').setAttribute('aria-label', pressed ? 'Show API key' : 'Hide API key');
});

function updateApiKeyState() {
  const hasKey = Boolean(qs('api-key').value.trim());
  qs('api-key-status').textContent = hasKey ? 'Key added for this session.' : 'Add a key to enable evaluation.';
  qs('key-trigger-status').textContent = hasKey ? 'Added' : 'Not set';
  qs('clear-api-key').disabled = !qs('api-key').value;
  updateEvaluateButtonState();
}

function clearApiKey() {
  qs('api-key').value = '';
  qs('api-key').type = 'password';
  qs('toggle-api-key').title = 'Show API key';
  qs('toggle-api-key').setAttribute('aria-pressed', 'false');
  qs('toggle-api-key').setAttribute('aria-label', 'Show API key');
  updateApiKeyState();
}

qs('session-access').addEventListener('toggle', (event) => {
  if (event.newState === 'open') {
    qs('api-key').focus();
  } else {
    qs('api-key').type = 'password';
    qs('toggle-api-key').title = 'Show API key';
    qs('toggle-api-key').setAttribute('aria-pressed', 'false');
    qs('toggle-api-key').setAttribute('aria-label', 'Show API key');
  }
});
qs('api-key').addEventListener('input', updateApiKeyState);
qs('clear-api-key').addEventListener('click', () => {
  clearApiKey();
  qs('api-key').focus();
});
window.addEventListener('pagehide', clearApiKey);
window.addEventListener('pageshow', clearApiKey);

qs('copy-text').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(state.pageText);
    qs('copy-text').textContent = 'Copied';
    setTimeout(() => { qs('copy-text').textContent = 'Copy text'; }, 1500);
  } catch (error) {
    setUploadStatus('Could not copy text to the clipboard.', true);
  }
});

async function loadSampleQuestions() {
  const response = await apiFetch('/api/sample-questions');
  const body = await response.json();
  qs('questions').value = formatQuestionsForDisplay(body.text);
  updateEvaluateButtonState();
}

loadSamples();
loadSampleQuestions();
updateEvaluateButtonState();

function renderTextOutput() {
  const output = qs('text-output');
  if (!state.pageText.trim()) {
    output.textContent = 'No extractable text was found on this page.';
    output.classList.add('text-light');
  } else {
    output.textContent = state.pageText;
    output.classList.remove('text-light');
  }
}

async function loadPage(pageNumber) {
  const token = ++state.loadToken;
  state.pageNumber = pageNumber;
  qs('grid').setAttribute('aria-busy', 'true');
  const response = await apiFetch(`/api/documents/${state.documentId}/pages/${pageNumber}/items`);
  const body = await response.json();
  if (token !== state.loadToken) return; // a newer page load superseded this one
  state.pageItems = body.items;
  state.pageText = body.text;
  renderTextOutput();
  renderResults();
  updateToolbar();
  updateEvaluateButtonState();
  await renderPreview();
  qs('grid').removeAttribute('aria-busy');
}

function updateToolbar() {
  qs('page-indicator').textContent = `Page ${state.pageNumber} of ${state.pageCount}`;
  qs('prev-page').disabled = state.pageNumber === 1;
  qs('next-page').disabled = state.pageNumber === state.pageCount;
}

qs('prev-page').addEventListener('click', () => loadPage(state.pageNumber - 1));
qs('next-page').addEventListener('click', () => loadPage(state.pageNumber + 1));

function currentQuestions() {
  return parseQuestions(qs('questions').value);
}

function visibleItemIds() {
  if (!state.showBoxes) return [];
  const latest = state.pageResults[state.pageNumber];
  if (!latest || !latest.answers) return [];
  const visible = [];
  state.pageItems.forEach((item, index) => {
    const hit = Object.values(latest.answers).some((answer) => {
      const probability = answer.probabilities[String(index)];
      return probability !== undefined && probability !== null && probability >= state.threshold;
    });
    if (hit) visible.push(item.id);
  });
  return visible;
}

function topAnswersFor(answer) {
  const ranked = state.pageItems.map((item, index) => ({
    item, probability: answer.probabilities[String(index)] ?? null,
  })).sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
  return ranked.slice(0, 2);
}

function appendMatch(container, match) {
  const { item, probability } = match;
  const level = probability >= 0.8 ? 'high' : probability >= 0.5 ? 'medium' : 'low';
  const text = document.createElement('p');
  text.className = 'answer-text';
  text.textContent = item.text.length > 180 ? `${item.text.slice(0, 180)}...` : item.text;
  const label = document.createElement('small');
  label.className = `probability-label ${level}`;
  label.textContent = `${(probability * 100).toFixed(1)}% match probability / ${level}`;
  const meter = document.createElement('div');
  meter.className = `probability-meter ${level}`;
  meter.setAttribute('role', 'meter');
  meter.setAttribute('aria-label', 'Match probability');
  meter.setAttribute('aria-valuemin', '0');
  meter.setAttribute('aria-valuemax', '100');
  meter.setAttribute('aria-valuenow', String(probability * 100));
  const fill = document.createElement('span');
  fill.style.width = `${probability * 100}%`;
  meter.appendChild(fill);
  container.append(text, label, meter);
  if (item.text.length > 180) {
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'ghost small';
    more.textContent = 'View full match';
    more.addEventListener('click', () => {
      qs('full-answer').textContent = item.text;
      qs('answer-dialog').showModal();
    });
    container.appendChild(more);
  }
}

function renderResults() {
  const pane = qs('results-pane');
  const latest = state.pageResults[state.pageNumber];
  pane.innerHTML = '';
  const questions = currentQuestions();
  if (!latest || !latest.answers) {
    const message = document.createElement('p');
    message.className = 'text-light';
    message.textContent = state.evaluating ? 'Evaluating selected pages...' : latest?.error
      ? `Evaluation failed: ${latest.error}` : latest?.skipped
      ? 'This page has no readable text, even after OCR.' : state.batchSummary
      ? 'This page was not included in the evaluation. Change the page scope and run again.'
      : 'Review your questions, then select Run evaluation to see answers here.';
    pane.appendChild(message);
    return;
  }
  questions.forEach((question, index) => {
    const card = document.createElement('article');
    card.className = 'result-card';
    const heading = document.createElement('h3');
    heading.textContent = question;
    card.appendChild(heading);
    const answer = latest.answers[`q${index + 1}`];
    const matches = answer ? topAnswersFor(answer).filter(({ probability }) => Number.isFinite(probability)) : [];
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No answer returned for this question.';
      card.appendChild(empty);
    } else {
      appendMatch(card, matches[0]);
      if (matches.length > 1) {
        const alternatives = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'Alternative match';
        alternatives.appendChild(summary);
        appendMatch(alternatives, matches[1]);
        card.appendChild(alternatives);
      }
    }
    pane.appendChild(card);
  });
}

async function renderPreview() {
  const frame = qs('preview-frame');
  const renderScale = state.scale;
  const visible = visibleItemIds();
  const url = `/api/documents/${state.documentId}/pages/${state.pageNumber}/render`
    + `?scale=${renderScale}&highlight=${visible.join(',')}`;
  const token = state.loadToken;
  const response = await apiFetch(url);
  if (token !== state.loadToken) return;
  if (!response.ok) {
    frame.innerHTML = '<p class="error-text">Could not render this page.</p>';
    return;
  }
  const width = response.headers.get('X-Image-Width');
  const height = response.headers.get('X-Image-Height');
  const blob = await response.blob();
  if (token !== state.loadToken) return;
  const objectUrl = URL.createObjectURL(blob);
  const oldImage = frame.querySelector('img');
  if (oldImage) URL.revokeObjectURL(oldImage.src);
  const img = document.createElement('img');
  img.src = objectUrl;
  img.alt = `Page ${state.pageNumber} of ${state.filename}`;
  img.width = Number(width);
  img.height = Number(height);
  img.dataset.renderScale = String(renderScale);
  frame.replaceChildren(img);
  applyPreviewZoom();

  const latest = state.pageResults[state.pageNumber];
  const timingParts = [];
  if (latest && latest.render_seconds !== undefined) timingParts.push(`Render: ${latest.render_seconds.toFixed(3)}s`);
  if (latest && latest.eval_seconds !== undefined) timingParts.push(`Evaluation: ${latest.eval_seconds.toFixed(3)}s`);
  qs('page-timing').textContent = timingParts.length ? `Page ${state.pageNumber} · ${timingParts.join(' · ')}` : '';
  qs('preview-meta').textContent = `${visible.length} of ${state.pageItems.length} chunks highlighted`;
}

function applyPreviewZoom() {
  const stage = qs('preview-stage');
  const img = qs('preview-frame').querySelector('img');
  if (!img) return;
  const pageWidth = Number(img.getAttribute('width')) / Number(img.dataset.renderScale);
  const pageHeight = Number(img.getAttribute('height')) / Number(img.dataset.renderScale);
  const availableWidth = Math.max(1, stage.clientWidth - 16);
  if (state.previewMode === 'width') state.zoom = availableWidth / pageWidth;
  if (state.previewMode === 'page') state.zoom = Math.min(availableWidth / pageWidth, Math.max(1, stage.clientHeight - 16) / pageHeight);
  img.style.width = `${pageWidth * state.zoom}px`;
  qs('zoom-level').textContent = `${Math.round(state.zoom * 100)}%`;
  qs('zoom-out').disabled = state.zoom <= 0.25;
  qs('zoom-in').disabled = state.zoom >= 4;
  qs('fit-width').setAttribute('aria-pressed', String(state.previewMode === 'width'));
  qs('fit-page').setAttribute('aria-pressed', String(state.previewMode === 'page'));
}

for (const mode of ['width', 'page']) {
  qs(`fit-${mode}`).addEventListener('click', () => {
    state.previewMode = mode;
    applyPreviewZoom();
    qs('preview-stage').scrollTo(0, 0);
  });
}
for (const [id, delta] of [['zoom-out', -0.25], ['zoom-in', 0.25]]) {
  qs(id).addEventListener('click', () => {
    state.previewMode = 'custom';
    state.zoom = Math.max(0.25, Math.min(4, state.zoom + delta));
    applyPreviewZoom();
  });
}
new ResizeObserver(applyPreviewZoom).observe(qs('preview-stage'));

function updateEvaluateButtonState() {
  const button = qs('evaluate-button');
  const hint = qs('evaluate-hint');
  if (!state.documentId) {
    button.disabled = true;
    hint.textContent = 'Upload a document to enable evaluation.';
    return;
  }
  if (state.evaluating) {
    button.disabled = true;
    hint.textContent = 'Evaluation in progress…';
    return;
  }
  if (qs('page-scope').value === 'first' && !qs('page-limit').checkValidity()) {
    button.disabled = true;
    hint.textContent = 'Enter a whole number of pages from 1 to 200.';
    return;
  }
  if (!currentQuestions().length) {
    button.disabled = true;
    hint.textContent = 'Add at least one question to enable evaluation.';
    return;
  }
  if (state.model === 'jev' && !qs('api-key').value.trim()) {
    button.disabled = true;
    hint.textContent = 'Add your API key using the button in the header to evaluate.';
    return;
  }
  button.disabled = false;
  const count = Math.min(selectedPageLimit() ?? state.pageCount, state.pageCount);
  hint.textContent = `Runs on ${count} of ${state.pageCount} pages, starting at page 1.`;
}

qs('evaluate-button').addEventListener('click', runBatchEvaluate);

function renderBatchSummary() {
  const summary = state.batchSummary;
  const panel = qs('batch-summary');
  if (!summary) { panel.hidden = true; return; }
  panel.hidden = false;
  qs('summary-caption').textContent = `Pages: ${summary.page_count} | Total time: ${summary.total_seconds.toFixed(3)} s`;

}

async function runBatchEvaluate() {
  const questions = currentQuestions();
  const apiKey = qs('api-key').value.trim();
  if ((state.model === 'jev' && !apiKey) || !state.documentId || state.evaluating) return;
  if (qs('page-scope').value === 'first' && !qs('page-limit').reportValidity()) return;
  const docAtRequest = state.documentId;
  if (!questions.length) return; // batch needs questions loaded; silently no-ops otherwise
  const pageLimit = selectedPageLimit();
  const count = Math.min(pageLimit ?? state.pageCount, state.pageCount);
  state.evaluating = true;
  state.pageResults = {};
  state.batchSummary = null;
  renderResults();
  renderBatchSummary();
  updateEvaluateButtonState();
  qs('questions').disabled = true;
  qs('page-scope').disabled = true;
  qs('page-limit').disabled = true;
  qs('replace-pdf').disabled = true;
  qs('evaluate-button').textContent = 'Evaluating...';
  const progress = qs('batch-progress');
  progress.hidden = false;
  qs('batch-progress-text').textContent = `Evaluating ${count} page(s)…`;
  try {
    await renderPreview();
    const response = await apiFetch(`/api/documents/${docAtRequest}/evaluate-batch`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ questions, api_key: apiKey, page_limit: pageLimit, model: state.model }),
    });
    const body = await response.json();
    if (!response.ok) {
      setUploadStatus(body.detail, true);
      return;
    }
    if (docAtRequest !== state.documentId) return;
    state.pageResults = body.page_stats;
    setUploadStatus('', false);
    state.batchSummary = body;
    renderBatchSummary();
    renderResults();
    await renderPreview();
  } catch (error) {
    setUploadStatus('Batch evaluation failed: could not reach the server.', true);
  } finally {
    progress.hidden = true;
    state.evaluating = false;
    qs('questions').disabled = false;
    qs('page-scope').disabled = false;
    qs('page-limit').disabled = false;
    qs('replace-pdf').disabled = false;
    qs('evaluate-button').textContent = 'Run evaluation';
    updateEvaluateButtonState();
    renderResults();
  }
}

qs('model-select').addEventListener('change', (event) => {
  state.model = event.target.value;
  const isAtom = state.model === 'atom';
  qs('model-name').textContent = isAtom ? 'ATOM' : 'Jev';
  qs('session-menu').hidden = isAtom; // ATOM needs no API key
  qs('send-hint').textContent = `Evaluation sends text from the selected pages to ${isAtom ? 'ATOM (at0m.pienomial.com)' : 'TypeSafe'}.`;
  state.pageResults = {};
  state.batchSummary = null;
  qs('batch-summary').hidden = true;
  updateEvaluateButtonState();
  if (state.documentId) {
    renderResults();
    renderPreview();
  }
});

qs('questions').addEventListener('input', () => {
  updateEvaluateButtonState();
});
qs('questions').addEventListener('change', () => {
  state.pageResults = {};
  state.batchSummary = null;
  qs('batch-summary').hidden = true;
  if (state.documentId) {
    renderResults();
    renderPreview();
  }
});

function selectedPageLimit() {
  return qs('page-scope').value === 'first' ? Number(qs('page-limit').value) : null;
}

function updatePageScope() {
  qs('page-limit-field').hidden = qs('page-scope').value !== 'first';
  updateEvaluateButtonState();
}
qs('page-scope').addEventListener('change', updatePageScope);
qs('page-limit').addEventListener('input', updatePageScope);

qs('open-text').addEventListener('click', () => qs('text-dialog').showModal());
