const keyInput = document.querySelector('#admin-key');
const notice = document.querySelector('#notice');
const rows = document.querySelector('#lead-rows');
const metrics = document.querySelector('#metrics');
const filter = document.querySelector('#status-filter');
const pauseButton = document.querySelector('#pause');
let leads = [];
let state = null;

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
  notice.style.color = error ? '#ff7b72' : '';
}

function renderState() {
  const selected = ['discovered', 'awaiting_approval', 'approved', 'generating', 'ready_to_publish', 'published'];
  metrics.innerHTML = selected.map(status => `<article class="metric"><strong>${state?.counts?.[status] || 0}</strong><span>${status.replaceAll('_', ' ')}</span></article>`).join('');
  pauseButton.textContent = state?.paused ? 'Resume' : 'Pause';
  pauseButton.classList.toggle('active', Boolean(state?.paused));
  const statuses = Object.keys(state?.counts || {});
  filter.innerHTML = '<option value="">All statuses</option>' + statuses.map(status => `<option value="${status}">${status.replaceAll('_', ' ')}</option>`).join('');
}

function renderLeads() {
  const selected = filter.value;
  const visible = selected ? leads.filter(lead => lead.status === selected) : leads;
  if (!visible.length) {
    rows.innerHTML = '<tr><td colspan="7" class="empty">No matching leads.</td></tr>';
    return;
  }
  rows.innerHTML = visible.map(lead => `<tr>
    <td><strong>${escapeHtml(lead.name)}</strong><small>${escapeHtml(lead.category || 'Uncategorized')}</small></td>
    <td>${escapeHtml(lead.city || '—')}</td>
    <td>${lead.rating ?? '—'} <small>(${lead.review_count})</small></td>
    <td class="score">${lead.score}</td>
    <td><span class="badge">${escapeHtml(lead.status.replaceAll('_', ' '))}</span></td>
    <td>${escapeHtml(lead.contact || '—')}</td>
    <td><div class="row-actions"><button data-details="${lead.id}">Details</button>${lead.status === 'awaiting_approval' ? `<button class="primary" data-approve="${lead.id}">Approve</button><button data-reject="${lead.id}">Reject</button>` : ''}</div></td>
  </tr>`).join('');
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[char]));
}

async function refresh() {
  try {
    document.querySelector('#health').textContent = 'Loading';
    const health = await fetch('/api/health').then(r => r.json());
    document.querySelector('#health').textContent = health.status;
    [state, leads] = await Promise.all([api('/api/state'), api('/api/leads')]);
    renderState();
    renderLeads();
  } catch (error) {
    setNotice(error.message, true);
    document.querySelector('#health').textContent = 'Locked';
  }
}

document.querySelector('#discover-form').addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  try {
    setNotice('Starting discovery…');
    const result = await api('/api/discover', {method: 'POST', body: JSON.stringify({
      categories: data.get('categories').split(',').map(v => v.trim()).filter(Boolean),
      cities: data.get('cities').split(',').map(v => v.trim()).filter(Boolean),
      minimum_rating: Number(data.get('rating')),
      minimum_reviews: Number(data.get('reviews')),
      max_businesses: Number(data.get('maximum')),
      include_no_website: true,
      include_outdated_website: true,
    })});
    setNotice(`Added ${result.created} businesses. ${result.skipped} skipped.`);
    await refresh();
  } catch (error) { setNotice(error.message, true); }
});

rows.addEventListener('click', async event => {
  const approve = event.target.dataset.approve;
  const reject = event.target.dataset.reject;
  const details = event.target.dataset.details;
  try {
    if (approve) await api(`/api/leads/${approve}/approve`, {method: 'POST', body: '{}'});
    if (reject) await api(`/api/leads/${reject}/reject`, {method: 'POST', body: '{}'});
    if (details) {
      const lead = leads.find(item => item.id === Number(details));
      document.querySelector('#details-body').innerHTML = `<h2>${escapeHtml(lead.name)}</h2><p>Qualification score: <strong>${lead.score}</strong></p><ul class="reason-list">${(lead.score_reasons || []).map(reason => `<li>${escapeHtml(reason)}</li>`).join('')}</ul>${lead.website_url ? `<p><a href="${escapeHtml(lead.website_url)}" target="_blank" rel="noreferrer">Current website</a></p>` : ''}`;
      document.querySelector('#details').showModal();
    } else if (approve || reject) {
      await refresh();
    }
  } catch (error) { setNotice(error.message, true); }
});

document.querySelector('#details .close').addEventListener('click', () => document.querySelector('#details').close());
filter.addEventListener('change', renderLeads);
document.querySelector('#refresh').addEventListener('click', refresh);
pauseButton.addEventListener('click', async () => {
  try {
    await api('/api/system/pause', {method: 'POST', body: JSON.stringify({paused: !state.paused, reason: state.paused ? null : 'Paused from control centre'})});
    await refresh();
  } catch (error) { setNotice(error.message, true); }
});
refresh();
