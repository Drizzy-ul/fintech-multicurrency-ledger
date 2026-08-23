/**
 * Antigravity FinTech - Dashboard Interactive Application
 */

const API_BASE = '/api/v1';

// Global State
const state = {
  token: localStorage.getItem('fintech_token') || null,
  user: null,
  wallets: [],
  liveRates: { 'USD:GHS': null, 'USD:GBP': null, 'GBP:GHS': null },
  currentQuote: null,
  quoteTimerInterval: null,
  quoteTimeRemaining: 0,
};

// UI Elements
const elements = {
  totalUsdEstimate: document.getElementById('total-usd-estimate'),
  usdBalance: document.getElementById('usd-balance'),
  ghsBalance: document.getElementById('ghs-balance'),
  gbpBalance: document.getElementById('gbp-balance'),
  
  tickerUsdGhs: document.getElementById('ticker-usd-ghs'),
  tickerUsdGbp: document.getElementById('ticker-usd-gbp'),
  tickerGbpGhs: document.getElementById('ticker-gbp-ghs'),

  userName: document.getElementById('user-name'),
  userEmail: document.getElementById('user-email'),
  userAvatar: document.getElementById('user-avatar'),

  // Convert Form
  convertSrcCurr: document.getElementById('convert-source-currency'),
  convertTgtCurr: document.getElementById('convert-target-currency'),
  convertAmount: document.getElementById('convert-amount'),
  btnGetQuote: document.getElementById('btn-get-quote'),
  quotePreviewBox: document.getElementById('quote-preview-box'),
  quoteRateText: document.getElementById('quote-rate-text'),
  quoteFeeText: document.getElementById('quote-fee-text'),
  quotePayoutText: document.getElementById('quote-payout-text'),
  quoteProgressBar: document.getElementById('quote-progress-bar'),
  btnExecuteConvert: document.getElementById('btn-execute-convert'),

  // P2P Form
  p2pRecipient: document.getElementById('p2p-recipient'),
  p2pSrcCurr: document.getElementById('p2p-src-curr'),
  p2pTgtCurr: document.getElementById('p2p-tgt-curr'),
  p2pAmount: document.getElementById('p2p-amount'),
  p2pDesc: document.getElementById('p2p-desc'),
  btnSendP2P: document.getElementById('btn-send-p2p'),

  // Audit
  auditBadge: document.getElementById('audit-status-badge'),
  auditMessage: document.getElementById('audit-message'),
  auditDetails: document.getElementById('audit-details'),

  // Ledger Table
  ledgerTableBody: document.getElementById('ledger-table-body'),

  // Statement Form
  stmtWalletSelect: document.getElementById('stmt-wallet-select'),
  stmtStartDate: document.getElementById('stmt-start-date'),
  stmtEndDate: document.getElementById('stmt-end-date'),
  btnGenerateStmt: document.getElementById('btn-generate-statement'),
  stmtStatusBox: document.getElementById('stmt-status-box'),

  // Modals
  depositModal: document.getElementById('deposit-modal'),
  authModal: document.getElementById('auth-modal'),
  toastContainer: document.getElementById('toast-container'),
};

// Toast notification helper
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
    <span>${message}</span>
  `;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Format Currency
function formatMoney(amount, currency) {
  const num = parseFloat(amount) || 0;
  const symbols = { USD: '$', GBP: '£', GHS: 'GH₵ ' };
  const sym = symbols[currency] || `${currency} `;
  return `${sym}${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Authenticated Fetch Wrapper
async function apiRequest(endpoint, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  if (!headers['Content-Type'] && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Token expired or invalid
    state.token = null;
    localStorage.removeItem('fintech_token');
    showAuthModal();
    throw new Error('Unauthorized');
  }

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || 'Request failed');
  }
  return data;
}

// Auto Login / Demo Login
async function ensureAuthenticated() {
  if (state.token) {
    try {
      state.user = await apiRequest('/auth/me');
      updateUserUI();
      return;
    } catch (e) {
      console.warn('Session expired, logging in default demo account...');
    }
  }

  // Attempt default login or registration for seamless demo
  try {
    const loginRes = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'demo.developer@antigravity.io', password: 'FintechDev2026!' })
    });

    if (loginRes.ok) {
      const data = await loginRes.json();
      state.token = data.access_token;
      localStorage.setItem('fintech_token', state.token);
      state.user = await apiRequest('/auth/me');
      updateUserUI();
      return;
    }

    // Otherwise register demo user
    const regRes = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'demo.developer@antigravity.io',
        password: 'FintechDev2026!',
        full_name: 'Kofi Mensah'
      })
    });

    if (regRes.ok) {
      const loginRes2 = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'demo.developer@antigravity.io', password: 'FintechDev2026!' })
      });
      const data2 = await loginRes2.json();
      state.token = data2.access_token;
      localStorage.setItem('fintech_token', state.token);
      state.user = await apiRequest('/auth/me');
      updateUserUI();
    }
  } catch (err) {
    console.error('Auth error:', err);
    showAuthModal();
  }
}

function updateUserUI() {
  if (!state.user) return;
  elements.userName.textContent = state.user.full_name;
  elements.userEmail.textContent = state.user.email;
  elements.userAvatar.textContent = state.user.full_name.charAt(0).toUpperCase();
}

// Refresh Live Rates
async function refreshLiveRates() {
  try {
    const q1 = await apiRequest('/transfers/quote', {
      method: 'POST',
      body: JSON.stringify({ source_currency: 'USD', target_currency: 'GHS', amount: '1.00' })
    });
    const q2 = await apiRequest('/transfers/quote', {
      method: 'POST',
      body: JSON.stringify({ source_currency: 'USD', target_currency: 'GBP', amount: '1.00' })
    });
    const q3 = await apiRequest('/transfers/quote', {
      method: 'POST',
      body: JSON.stringify({ source_currency: 'GBP', target_currency: 'GHS', amount: '1.00' })
    });

    elements.tickerUsdGhs.textContent = `1 USD = ${parseFloat(q1.exchange_rate).toFixed(4)} GHS`;
    elements.tickerUsdGbp.textContent = `1 USD = ${parseFloat(q2.exchange_rate).toFixed(4)} GBP`;
    elements.tickerGbpGhs.textContent = `1 GBP = ${parseFloat(q3.exchange_rate).toFixed(4)} GHS`;
  } catch (e) {
    console.warn('Rates refresh:', e);
  }
}

// Refresh User Wallets
async function refreshWallets() {
  try {
    const overview = await apiRequest('/wallets');
    state.wallets = overview.wallets || [];

    const usd = state.wallets.find(w => w.currency === 'USD');
    const ghs = state.wallets.find(w => w.currency === 'GHS');
    const gbp = state.wallets.find(w => w.currency === 'GBP');

    elements.usdBalance.textContent = formatMoney(usd ? usd.balance : 0, 'USD');
    elements.ghsBalance.textContent = formatMoney(ghs ? ghs.balance : 0, 'GHS');
    elements.gbpBalance.textContent = formatMoney(gbp ? gbp.balance : 0, 'GBP');

    elements.totalUsdEstimate.textContent = formatMoney(overview.total_in_usd_estimate || 0, 'USD');

    // Populate statement wallet selector
    elements.stmtWalletSelect.innerHTML = '';
    state.wallets.forEach(w => {
      const opt = document.createElement('option');
      opt.value = w.id;
      opt.textContent = `${w.currency} Wallet (#${w.id}) - Bal: ${formatMoney(w.balance, w.currency)}`;
      elements.stmtWalletSelect.appendChild(opt);
    });
  } catch (err) {
    console.error('Wallets error:', err);
  }
}

// Refresh Double-Entry Ledger History
async function refreshLedgerHistory() {
  try {
    const postings = await apiRequest('/ledger/history?limit=25');
    elements.ledgerTableBody.innerHTML = '';

    if (!postings || postings.length === 0) {
      elements.ledgerTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 24px; color: var(--text-sub);">No ledger transactions recorded yet.</td></tr>`;
      return;
    }

    postings.forEach(p => {
      const tr = document.createElement('tr');
      const isDebit = p.direction === 'DEBIT';
      const dirClass = isDebit ? 'direction-debit' : 'direction-credit';
      const sign = isDebit ? '+' : '-';
      const dt = new Date(p.created_at).toLocaleString();

      tr.innerHTML = `
        <td><font color="#94A3B8">${dt}</font></td>
        <td><span class="currency-badge badge-${p.currency.toLowerCase()}">${p.currency}</span></td>
        <td><span style="font-size:0.75rem; color: #CBD5E0; font-family: var(--font-mono);">${p.account_type}</span></td>
        <td class="${dirClass}"><b>${sign}${formatMoney(p.amount, p.currency)}</b></td>
        <td><font color="#A0AEC0">${p.balance_after ? formatMoney(p.balance_after, p.currency) : '—'}</font></td>
      `;
      elements.ledgerTableBody.appendChild(tr);
    });
  } catch (err) {
    console.error('Ledger error:', err);
  }
}

// Run Double-Entry Ledger Audit
async function runLedgerAudit() {
  try {
    const audit = await apiRequest('/ledger/audit');
    if (audit.is_balanced) {
      elements.auditBadge.className = 'currency-badge badge-gbp';
      elements.auditBadge.innerHTML = '<i class="fas fa-check-circle"></i> ZERO-SUM BALANCED';
      elements.auditMessage.innerHTML = `<b>${audit.total_journal_entries}</b> Journal Entries & <b>${audit.total_postings}</b> Postings audited with <b>0</b> imbalances.`;
    } else {
      elements.auditBadge.className = 'currency-badge badge-ghs';
      elements.auditBadge.innerHTML = '<i class="fas fa-exclamation-triangle"></i> IMBALANCE DETECTED';
      elements.auditMessage.textContent = audit.message;
    }

    let detailHtml = '<div style="display:flex; gap: 16px; flex-wrap: wrap; margin-top: 10px;">';
    for (const [curr, stats] of Object.entries(audit.currency_balances || {})) {
      detailHtml += `
        <div style="background: rgba(0,0,0,0.3); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
          <b style="color:var(--accent-cyan);">${curr}:</b> Debits: ${stats.total_debits} | Credits: ${stats.total_credits} (Diff: ${stats.net_difference})
        </div>
      `;
    }
    detailHtml += '</div>';
    elements.auditDetails.innerHTML = detailHtml;
  } catch (err) {
    console.error('Audit error:', err);
  }
}

// Request Live FX Quote
elements.btnGetQuote.addEventListener('click', async () => {
  const src = elements.convertSrcCurr.value;
  const tgt = elements.convertTgtCurr.value;
  const amount = elements.convertAmount.value;

  if (!amount || parseFloat(amount) <= 0) {
    showToast('Please enter a positive amount to convert.', 'error');
    return;
  }

  if (src === tgt) {
    showToast('Source and Target currencies must be different.', 'error');
    return;
  }

  try {
    elements.btnGetQuote.disabled = true;
    elements.btnGetQuote.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Locking Quote...';

    const quote = await apiRequest('/transfers/quote', {
      method: 'POST',
      body: JSON.stringify({
        source_currency: src,
        target_currency: tgt,
        amount: parseFloat(amount).toFixed(2)
      })
    });

    state.currentQuote = quote;
    state.quoteTimeRemaining = 60;

    // Show Preview Box
    elements.quoteRateText.textContent = `1 ${src} = ${parseFloat(quote.exchange_rate).toFixed(6)} ${tgt}`;
    elements.quoteFeeText.textContent = `${formatMoney(quote.fee_amount, src)} (0.5%)`;
    elements.quotePayoutText.textContent = `${formatMoney(quote.target_amount, tgt)}`;
    elements.quotePreviewBox.classList.add('active');

    // Start Countdown Bar
    if (state.quoteTimerInterval) clearInterval(state.quoteTimerInterval);
    elements.quoteProgressBar.style.width = '100%';

    state.quoteTimerInterval = setInterval(() => {
      state.quoteTimeRemaining -= 1;
      const pct = (state.quoteTimeRemaining / 60) * 100;
      elements.quoteProgressBar.style.width = `${pct}%`;

      if (state.quoteTimeRemaining <= 0) {
        clearInterval(state.quoteTimerInterval);
        state.currentQuote = null;
        elements.quotePreviewBox.classList.remove('active');
        showToast('Quote expired. Please request a fresh rate.', 'info');
      }
    }, 1000);

    showToast('Live FX rate quote locked for 60 seconds!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    elements.btnGetQuote.disabled = false;
    elements.btnGetQuote.innerHTML = '<i class="fas fa-calculator"></i> Get Live FX Quote';
  }
});

// Execute FX Conversion
elements.btnExecuteConvert.addEventListener('click', async () => {
  if (!state.currentQuote) {
    showToast('Quote has expired. Request a new quote first.', 'error');
    return;
  }

  try {
    elements.btnExecuteConvert.disabled = true;
    elements.btnExecuteConvert.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Executing Conversion...';

    const result = await apiRequest('/transfers/convert', {
      method: 'POST',
      body: JSON.stringify({
        source_currency: state.currentQuote.source_currency,
        target_currency: state.currentQuote.target_currency,
        amount: state.currentQuote.source_amount,
        quote_id: state.currentQuote.quote_id
      })
    });

    if (state.quoteTimerInterval) clearInterval(state.quoteTimerInterval);
    elements.quotePreviewBox.classList.remove('active');
    state.currentQuote = null;
    elements.convertAmount.value = '';

    showToast(result.message, 'success');
    await refreshWallets();
    await refreshLedgerHistory();
    await runLedgerAudit();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    elements.btnExecuteConvert.disabled = false;
    elements.btnExecuteConvert.innerHTML = '<i class="fas fa-check"></i> Confirm & Execute Conversion';
  }
});

// P2P Transfer
elements.btnSendP2P.addEventListener('click', async () => {
  const recipient = elements.p2pRecipient.value.trim();
  const src = elements.p2pSrcCurr.value;
  const tgt = elements.p2pTgtCurr.value;
  const amount = elements.p2pAmount.value;
  const desc = elements.p2pDesc.value.trim() || 'P2P Transfer';

  if (!recipient || !amount || parseFloat(amount) <= 0) {
    showToast('Please specify a valid recipient email and positive amount.', 'error');
    return;
  }

  try {
    elements.btnSendP2P.disabled = true;
    elements.btnSendP2P.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending Transfer...';

    const res = await apiRequest('/transfers/p2p', {
      method: 'POST',
      body: JSON.stringify({
        recipient_email: recipient,
        source_currency: src,
        target_currency: tgt,
        amount: parseFloat(amount).toFixed(2),
        description: desc
      })
    });

    showToast(res.message, 'success');
    elements.p2pRecipient.value = '';
    elements.p2pAmount.value = '';
    elements.p2pDesc.value = '';

    await refreshWallets();
    await refreshLedgerHistory();
    await runLedgerAudit();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    elements.btnSendP2P.disabled = false;
    elements.btnSendP2P.innerHTML = '<i class="fas fa-paper-plane"></i> Send Transfer';
  }
});

// Deposit Modal Actions
function openDepositModal(curr = 'USD') {
  document.getElementById('deposit-currency').value = curr;
  elements.depositModal.classList.add('active');
}

function closeDepositModal() {
  elements.depositModal.classList.remove('active');
}

document.getElementById('btn-submit-deposit').addEventListener('click', async () => {
  const curr = document.getElementById('deposit-currency').value;
  const amount = document.getElementById('deposit-amount').value;
  const desc = document.getElementById('deposit-desc').value || 'Bank Wire Deposit';

  if (!amount || parseFloat(amount) <= 0) {
    showToast('Please enter a valid deposit amount.', 'error');
    return;
  }

  try {
    await apiRequest('/wallets/deposit', {
      method: 'POST',
      body: JSON.stringify({
        currency: curr,
        amount: parseFloat(amount).toFixed(2),
        description: desc
      })
    });

    showToast(`Successfully deposited ${formatMoney(amount, curr)}!`, 'success');
    closeDepositModal();
    document.getElementById('deposit-amount').value = '';
    await refreshWallets();
    await refreshLedgerHistory();
    await runLedgerAudit();
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// Statement Generation
elements.btnGenerateStmt.addEventListener('click', async () => {
  const walletId = elements.stmtWalletSelect.value;
  const start = elements.stmtStartDate.value;
  const end = elements.stmtEndDate.value;

  if (!walletId || !start || !end) {
    showToast('Please choose a wallet and date range.', 'error');
    return;
  }

  try {
    elements.btnGenerateStmt.disabled = true;
    elements.btnGenerateStmt.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Compiling Statement...';

    const task = await apiRequest('/statements/generate', {
      method: 'POST',
      body: JSON.stringify({
        wallet_id: parseInt(walletId),
        start_date: start,
        end_date: end
      })
    });

    elements.stmtStatusBox.style.display = 'block';
    elements.stmtStatusBox.innerHTML = `
      <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 14px;">
        <p><i class="fas fa-cog fa-spin"></i> <b>Compiling PDF statement via Celery worker...</b></p>
        <p style="font-size:0.75rem; color:var(--text-sub); margin-top:4px;">Task ID: ${task.task_id}</p>
      </div>
    `;

    // Poll for status
    let attempts = 0;
    const pollInterval = setInterval(async () => {
      attempts += 1;
      try {
        const status = await apiRequest(`/statements/${task.task_id}/status`);
        if (status.status === 'SUCCESS') {
          clearInterval(pollInterval);
          elements.stmtStatusBox.innerHTML = `
            <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 8px; padding: 14px; display:flex; justify-content:space-between; align-items:center;">
              <div>
                <p style="color: #34D399; font-weight:700;"><i class="fas fa-file-pdf"></i> Statement Ready!</p>
                <p style="font-size:0.75rem; color:#A0AEC0;">File: ${status.filename} (${status.file_size_bytes} bytes)</p>
              </div>
              <a href="/api/v1/statements/download/${status.filename}" class="btn btn-primary btn-sm" download>
                <i class="fas fa-download"></i> Download PDF
              </a>
            </div>
          `;
          showToast('Statement PDF compiled successfully!', 'success');
          elements.btnGenerateStmt.disabled = false;
          elements.btnGenerateStmt.innerHTML = '<i class="fas fa-file-pdf"></i> Generate Monthly Statement';
        } else if (status.status === 'FAILED') {
          clearInterval(pollInterval);
          elements.stmtStatusBox.innerHTML = `<p style="color:var(--accent-rose);">Failed: ${status.error}</p>`;
          elements.btnGenerateStmt.disabled = false;
          elements.btnGenerateStmt.innerHTML = '<i class="fas fa-file-pdf"></i> Generate Monthly Statement';
        }
      } catch (e) {
        if (attempts > 15) {
          clearInterval(pollInterval);
          elements.btnGenerateStmt.disabled = false;
          elements.btnGenerateStmt.innerHTML = '<i class="fas fa-file-pdf"></i> Generate Monthly Statement';
        }
      }
    }, 1500);

  } catch (err) {
    showToast(err.message, 'error');
    elements.btnGenerateStmt.disabled = false;
    elements.btnGenerateStmt.innerHTML = '<i class="fas fa-file-pdf"></i> Generate Monthly Statement';
  }
});

// Initialize Date Pickers default (last 30 days)
function initDates() {
  const today = new Date();
  const prior = new Date();
  prior.setDate(today.getDate() - 30);

  elements.stmtStartDate.value = prior.toISOString().split('T')[0];
  elements.stmtEndDate.value = today.toISOString().split('T')[0];
}

// Initial App Boot
async function initApp() {
  initDates();
  await ensureAuthenticated();
  await refreshLiveRates();
  await refreshWallets();
  await refreshLedgerHistory();
  await runLedgerAudit();

  // Auto refresh rates every 30 seconds
  setInterval(refreshLiveRates, 30000);
}

document.addEventListener('DOMContentLoaded', initApp);
