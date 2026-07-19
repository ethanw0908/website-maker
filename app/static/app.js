const keyInput = document.querySelector('#admin-key');
const notice = document.querySelector('#notice');
const metrics = document.querySelector('#metrics');
const filter = document.querySelector('#status-filter');
const searchInput = document.querySelector('#lead-search');
const pauseButton = document.querySelector('#pause');
const selectAll = document.querySelector('#select-all-leads');
const bulkActions = document.querySelector('#bulk-actions');
const selectedCount = document.querySelector('#selected-count');

let state = null;
let leads = [];
let jobs = [];
let deployments = [];
let drafts = [];
let integrations = {};
let smtpSettings = {};
const selectedLeadIds = new Set();

keyInput.value = localStorage.getItem('localsite-admin-key') || '';
keyInput.addEventListener('change', () => localStorage.setItem('localsite-admin-key', keyInput.value));

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {'Content-Type': 'application/json', 'X-Admin-Key': keyInput.value, ...(options.headers || {})},
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function setNotice(message, error = false) {
  notice.textContent = message;
  notice.classList.toggle('error', error);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[char]));
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleString();
}

function link(url, label) {
  if (!url) return '<span class="muted">—</span>';
  try {
    const parsed = new URL(url);
    if (!['http:', 'https:'].includes(parsed.protocol)) return '<span class="muted">—</span>';
    return `<a href="${escapeHtml(parsed.href)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
  } catch { return '<span class="muted">—</span>'; }
}

function statusLabel(value) {
  return escapeHtml(String(value || 'unknown').replaceAll('_', ' '));
}

function renderState() {
  const shown = ['discovered', 'awaiting_approval', 'generating', 'ready_to_publish', 'published', 'client'];
  metrics.innerHTML = shown.map(status => `<article class="metric"><strong>${state?.counts?.[status] || 0}</strong><span>${statusLabel(status)}</span></article>`).join('');
  pauseButton.textContent = state?.paused ? 'Resume' : 'Pause';
  pauseButton.classList.toggle('active', Boolean(state?.paused));
  const previous = filter.value;
  const statuses = Object.keys(state?.counts || {});
  filter.innerHTML = '<option value="">All statuses</option>' + statuses.map(status => `<option value="${escapeHtml(status)}">${statusLabel(status)}</option>`).join('');
  filter.value = statuses.includes(previous) ? previous : '';
}

function visibleLeads() {
  const selectedStatus = filter.value;
  const query = searchInput.value.trim().toLowerCase();
  return leads.filter(lead => {
    if (selectedStatus && lead.status !== selectedStatus) return false;
    if (!query) return true;
    return [lead.name, lead.city, lead.category, lead.contact, lead.phone, lead.note, lead.status]
      .some(value => String(value || '').toLowerCase().includes(query));
  });
}

function updateBulkActions() {
  selectedCount.textContent = selectedLeadIds.size;
  bulkActions.classList.toggle('visible', selectedLeadIds.size > 0);
  const visibleIds = visibleLeads().map(lead => lead.id);
  const selectedVisible = visibleIds.filter(id => selectedLeadIds.has(id)).length;
  selectAll.checked = visibleIds.length > 0 && selectedVisible === visibleIds.length;
  selectAll.indeterminate = selectedVisible > 0 && selectedVisible < visibleIds.length;
}

function renderLeads() {
  const rows = document.querySelector('#lead-rows');
  const visible = visibleLeads();
  if (!visible.length) {
    rows.innerHTML = '<tr><td colspan="12" class="empty">No matching leads.</td></tr>';
    updateBulkActions();
    return;
  }
  rows.innerHTML = visible.map(lead => `<tr class="${selectedLeadIds.has(lead.id) ? 'selected-row' : ''}">
    <td class="select-column"><input type="checkbox" data-select-lead="${lead.id}" ${selectedLeadIds.has(lead.id) ? 'checked' : ''} aria-label="Select ${escapeHtml(lead.name)}"></td>
    <td><strong>${escapeHtml(lead.name)}</strong><small>${escapeHtml(lead.category || 'Uncategorised')}</small></td>
    <td>${escapeHtml(lead.city || '—')}</td>
    <td>${lead.rating ?? '—'} <small>(${lead.review_count || 0})</small></td>
    <td>${link(lead.website_url, 'Website')}</td>
    <td>${escapeHtml(lead.contact || '—')}</td>
    <td class="score">${lead.score}</td>
    <td><span class="badge ${lead.status === 'client' ? 'client' : ''}">${statusLabel(lead.status)}</span></td>
    <td>${link(lead.github_repository, 'Repository')}</td>
    <td>${link(lead.vercel_preview_url, 'Preview')}</td>
    <td><div class="note-cell"><input data-note-input="${lead.id}" value="${escapeHtml(lead.note || '')}" placeholder="Add note"><button data-save-note="${lead.id}">Save</button></div></td>
    <td><button data-details="${lead.id}">Details</button></td>
  </tr>`).join('');
  updateBulkActions();
}

function renderJobs() {
  const rows = document.querySelector('#job-rows');
  rows.innerHTML = jobs.length ? jobs.map(job => `<tr><td>${job.id}</td><td><strong>${escapeHtml(job.business)}</strong></td><td><span class="badge">${statusLabel(job.status)}</span></td><td>${job.revision_count ?? 0}</td><td>${formatDate(job.updated_at)}</td><td class="truncate" title="${escapeHtml(job.error || '')}">${escapeHtml(job.error || '—')}</td><td>${job.status === 'passed' ? `<button class="primary" data-publish="${job.id}">Publish</button>` : '—'}</td></tr>`).join('') : '<tr><td colspan="7" class="empty">No generation jobs.</td></tr>';
}

function renderDeployments() {
  const rows = document.querySelector('#deployment-rows');
  rows.innerHTML = deployments.length ? deployments.map(item => `<tr><td>${item.id}</td><td><strong>${escapeHtml(item.business)}</strong></td><td><span class="badge">${statusLabel(item.status)}</span></td><td>${link(item.github_repository, 'Repository')}</td><td>${link(item.preview_url, 'Preview')}</td><td><code>${escapeHtml((item.commit_sha || '—').slice(0, 10))}</code></td><td>${formatDate(item.created_at)}</td><td>${item.preview_url ? `<button data-create-draft="${item.id}">Create email draft</button>` : '—'}</td></tr>`).join('') : '<tr><td colspan="8" class="empty">No deployments.</td></tr>';
}

function renderDrafts() {
  const rows = document.querySelector('#draft-rows');
  rows.innerHTML = drafts.length ? drafts.map(draft => `<tr><td>${draft.id}</td><td><strong>${escapeHtml(draft.business)}</strong></td><td>${escapeHtml(draft.recipient)}</td><td class="truncate" title="${escapeHtml(draft.subject)}">${escapeHtml(draft.subject)}</td><td><span class="badge">${statusLabel(draft.status)}</span></td><td>${formatDate(draft.created_at)}</td><td><div class="row-actions"><button data-view-draft="${draft.id}">Review</button>${draft.status !== 'sent' ? `<button class="primary" data-send-draft="${draft.id}">Send</button>` : ''}</div></td></tr>`).join('') : '<tr><td colspan="7" class="empty">No email drafts.</td></tr>';
}

function renderIntegrations() {
  const items = [
    ['GitHub', integrations.github?.configured, integrations.github?.owner || 'Token not configured'],
    ['Codex', integrations.codex?.configured, integrations.codex?.authentication || 'OAuth not connected'],
    ['Vercel', integrations.vercel?.configured, integrations.vercel?.scope || 'Token not configured'],
    ['SMTP', integrations.smtp?.configured, integrations.smtp?.from_email || 'Mailbox not configured'],
  ];
  document.querySelector('#integration-grid').innerHTML = items.map(([name, configured, detail]) => `<article class="integration-card"><div><strong>${escapeHtml(name)}</strong><span>${escapeHtml(detail)}</span></div><span class="dot ${configured ? 'ok' : ''}"></span></article>`).join('');
}

function fillSmtpForm() {
  const form = document.querySelector('#smtp-form');
  for (const name of ['host','port','username','from_email','from_name','sender_business','postal_address','unsubscribe_email']) form.elements[name].value = smtpSettings[name] ?? '';
  form.elements.password.value = '';
  form.elements.use_tls.checked = Boolean(smtpSettings.use_tls);
  form.elements.use_ssl.checked = Boolean(smtpSettings.use_ssl);
  form.elements.enabled.checked = Boolean(smtpSettings.enabled);
  document.querySelector('#smtp-state').textContent = smtpSettings.configured ? (smtpSettings.enabled ? 'Configured' : 'Disabled') : 'Not configured';
}

async function refresh() {
  try {
    document.querySelector('#health').textContent = 'Loading';
    const health = await fetch('/api/health').then(response => response.json());
    document.querySelector('#health').textContent = health.status;
    [state, leads, jobs, deployments, drafts, integrations, smtpSettings] = await Promise.all([
      api('/api/state'), api('/api/leads'), api('/api/jobs'), api('/api/deployments'), api('/api/email-drafts'), api('/api/integrations'), api('/api/settings/smtp'),
    ]);
    const validIds = new Set(leads.map(lead => lead.id));
    for (const id of [...selectedLeadIds]) if (!validIds.has(id)) selectedLeadIds.delete(id);
    renderState(); renderLeads(); renderJobs(); renderDeployments(); renderDrafts(); renderIntegrations(); fillSmtpForm();
  } catch (error) {
    setNotice(error.message, true);
    document.querySelector('#health').textContent = 'Locked';
  }
}

async function runBulkAction(action) {
  const ids = [...selectedLeadIds];
  if (!ids.length) return;
  if (action === 'delete' && !window.confirm(`Delete ${ids.length} selected lead${ids.length === 1 ? '' : 's'} and all related jobs, deployments, and drafts? This cannot be undone.`)) return;
  const labels = {make_website: 'Queuing Codex website generation…', delete: 'Deleting selected leads…', sold: 'Moving selected leads to clients…'};
  try {
    setNotice(labels[action]);
    const result = await api('/api/leads/bulk-action', {method: 'POST', body: JSON.stringify({ids, action})});
    selectedLeadIds.clear();
    if (action === 'make_website') setNotice(`Queued ${result.queued} website${result.queued === 1 ? '' : 's'}. ${result.skipped?.length || 0} skipped.`);
    if (action === 'delete') setNotice(`Deleted ${result.deleted} lead${result.deleted === 1 ? '' : 's'}.`);
    if (action === 'sold') setNotice(`Moved ${result.updated} lead${result.updated === 1 ? '' : 's'} to client.`);
    await refresh();
  } catch (error) { setNotice(error.message, true); }
}

document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(item => item.classList.toggle('active', item === button));
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.dataset.panel === button.dataset.tab));
}));

document.querySelector('#discover-form').addEventListener('submit', async event => {
  event.preventDefault(); const data = new FormData(event.currentTarget);
  try {
    setNotice('Starting discovery…');
    const result = await api('/api/discover', {method:'POST', body:JSON.stringify({categories:data.get('categories').split(',').map(v=>v.trim()).filter(Boolean), cities:data.get('cities').split(',').map(v=>v.trim()).filter(Boolean), minimum_rating:Number(data.get('rating')), minimum_reviews:Number(data.get('reviews')), max_businesses:Number(data.get('maximum')), include_no_website:true, include_outdated_website:true})});
    setNotice(`Added ${result.created} businesses. ${result.skipped} skipped.`); await refresh();
  } catch (error) { setNotice(error.message, true); }
});

document.querySelector('#lead-rows').addEventListener('click', async event => {
  const select = event.target.dataset.selectLead;
  const saveNote = event.target.dataset.saveNote;
  const details = event.target.dataset.details;
  try {
    if (select) {
      const id = Number(select); event.target.checked ? selectedLeadIds.add(id) : selectedLeadIds.delete(id); renderLeads(); return;
    }
    if (saveNote) {
      const input = document.querySelector(`[data-note-input="${saveNote}"]`);
      await api(`/api/leads/${saveNote}/note`, {method:'PUT', body:JSON.stringify({content:input.value})}); setNotice('Note saved.'); await refresh(); return;
    }
    if (details) {
      const lead = leads.find(item => item.id === Number(details));
      document.querySelector('#details-body').innerHTML = `<h2>${escapeHtml(lead.name)}</h2><dl class="details-grid"><dt>Status</dt><dd>${statusLabel(lead.status)}</dd><dt>Score</dt><dd>${lead.score}</dd><dt>Phone</dt><dd>${escapeHtml(lead.phone || '—')}</dd><dt>Address</dt><dd>${escapeHtml(lead.address || '—')}</dd><dt>GitHub</dt><dd>${link(lead.github_repository, 'Open repository')}</dd><dt>Vercel</dt><dd>${link(lead.vercel_preview_url, 'Open preview')}</dd></dl><ul class="reason-list">${(lead.score_reasons || []).map(reason=>`<li>${escapeHtml(reason)}</li>`).join('')}</ul>`;
      document.querySelector('#details').showModal();
    }
  } catch (error) { setNotice(error.message, true); }
});

selectAll.addEventListener('change', () => { for (const lead of visibleLeads()) selectAll.checked ? selectedLeadIds.add(lead.id) : selectedLeadIds.delete(lead.id); renderLeads(); });
filter.addEventListener('change', renderLeads); searchInput.addEventListener('input', renderLeads);
document.querySelector('#make-website-selected').addEventListener('click', () => runBulkAction('make_website'));
document.querySelector('#delete-selected').addEventListener('click', () => runBulkAction('delete'));
document.querySelector('#sold-selected').addEventListener('click', () => runBulkAction('sold'));

document.querySelector('#job-rows').addEventListener('click', async event => {
  const jobId = event.target.dataset.publish; if (!jobId) return;
  try { setNotice('Publishing to GitHub and Vercel…'); await api(`/api/jobs/${jobId}/publish`, {method:'POST', body:JSON.stringify({repository_visibility:'private', deploy_to_vercel:true})}); setNotice('Published.'); await refresh(); } catch (error) { setNotice(error.message, true); }
});

document.querySelector('#deployment-rows').addEventListener('click', event => {
  const id = event.target.dataset.createDraft; if (!id) return;
  document.querySelector('#draft-form').elements.deployment_id.value = id; document.querySelector('#draft-dialog').showModal();
});

document.querySelector('#draft-form').addEventListener('submit', async event => {
  event.preventDefault(); const data = new FormData(event.currentTarget);
  try { await api(`/api/deployments/${data.get('deployment_id')}/email-draft`, {method:'POST', body:JSON.stringify({recipient:data.get('recipient')})}); document.querySelector('#draft-dialog').close(); event.currentTarget.reset(); setNotice('Email draft created.'); await refresh(); } catch (error) { setNotice(error.message, true); }
});

document.querySelector('#draft-rows').addEventListener('click', async event => {
  const view = event.target.dataset.viewDraft; const send = event.target.dataset.sendDraft;
  try {
    if (view) { const draft = drafts.find(item => item.id === Number(view)); document.querySelector('#details-body').innerHTML = `<h2>${escapeHtml(draft.subject)}</h2><p><strong>To:</strong> ${escapeHtml(draft.recipient)}</p><pre class="email-body">${escapeHtml(draft.body)}</pre>`; document.querySelector('#details').showModal(); }
    if (send && window.confirm('Send this email now through your configured SMTP account?')) { await api(`/api/email-drafts/${send}/send`, {method:'POST'}); setNotice('Email sent.'); await refresh(); }
  } catch (error) { setNotice(error.message, true); }
});

document.querySelector('#smtp-form').addEventListener('submit', async event => {
  event.preventDefault(); const data = new FormData(event.currentTarget);
  try { smtpSettings = await api('/api/settings/smtp', {method:'PUT', body:JSON.stringify({host:data.get('host'), port:Number(data.get('port')), username:data.get('username') || null, password:data.get('password') || null, from_email:data.get('from_email'), from_name:data.get('from_name') || null, sender_business:data.get('sender_business') || null, postal_address:data.get('postal_address') || null, unsubscribe_email:data.get('unsubscribe_email') || null, use_tls:data.has('use_tls'), use_ssl:data.has('use_ssl'), enabled:data.has('enabled')})}); setNotice('SMTP settings saved.'); await refresh(); } catch (error) { setNotice(error.message, true); }
});

document.querySelector('#test-smtp').addEventListener('click', async () => { try { setNotice('Testing SMTP connection…'); const result = await api('/api/settings/smtp/test', {method:'POST'}); setNotice(result.message); } catch (error) { setNotice(error.message, true); } });
document.querySelectorAll('dialog .close').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelector('#refresh').addEventListener('click', refresh);
pauseButton.addEventListener('click', async () => { try { await api('/api/system/pause', {method:'POST', body:JSON.stringify({paused:!state.paused, reason:state.paused ? null : 'Paused from control centre'})}); await refresh(); } catch (error) { setNotice(error.message, true); } });
refresh();
