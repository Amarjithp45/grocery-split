/**
 * SPLITKART Client Application
 * Clean 3-Tab Interface (Grocery, Split, Friends) + Groups System
 * Features:
 * - Groups: Create / Join groups via invite codes
 * - Real User Authentication & Registration (email-based)
 * - Permanent Admin: amarjithp45@gmail.com
 * - Online Presence & Last Login Tracking
 * - Euro (€) Currency across all splits and bills
 * - Mobile System Status Bar Notifications (Service Worker showNotification)
 * - Real-Time Server-Sent Events (SSE) Synchronization
 * - Web Audio API Synthesis
 */

// Application State
const state = {
  currentUser: null,
  authToken: localStorage.getItem('SPLITKART_token') || localStorage.getItem('palacharak_token') || localStorage.getItem('palachrakk_token') || localStorage.getItem('cartshare_token') || null,
  activeGroupId: localStorage.getItem('splitkart_group_id') !== null ? parseInt(localStorage.getItem('splitkart_group_id')) : null,
  activeGroup: JSON.parse(localStorage.getItem('splitkart_group') || 'null'),
  availableGroups: [],
  members: [],
  activeItems: [],
  boughtItems: [],
  bills: [],
  balances: [],
  transfers: [],
  activities: [],
  stats: {},
  activeTab: 'grocery',
  selectedCategory: 'All',
  soundEnabled: true,
  notificationsEnabled: false,
  isConnected: false
};

// =========================================================
// 1. AUTHENTICATION & SESSION MANAGEMENT
// =========================================================

function isUserAdmin() {
  if (!state.currentUser) return false;
  if (state.currentUser.is_admin === 1 || state.currentUser.is_admin === '1' || state.currentUser.is_admin === true) return true;
  if (state.currentUser.username && state.currentUser.username.toLowerCase() === 'amarjithp45@gmail.com') return true;
  return false;
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (state.authToken) {
    headers['Authorization'] = `Bearer ${state.authToken}`;
  }
  return headers;
}

function switchAuthTab(tab) {
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const loginTab = document.getElementById('auth-tab-login');
  const registerTab = document.getElementById('auth-tab-register');
  const errorBox = document.getElementById('auth-error');
  if (errorBox) errorBox.classList.add('hidden');

  if (tab === 'login') {
    loginForm.classList.remove('hidden');
    registerForm.classList.add('hidden');
    loginTab.className = 'flex-1 py-2 text-xs font-bold rounded-xl bg-white text-slate-900 shadow-sm transition';
    registerTab.className = 'flex-1 py-2 text-xs font-bold rounded-xl text-slate-500 hover:text-slate-800 transition';
  } else {
    loginForm.classList.add('hidden');
    registerForm.classList.remove('hidden');
    registerTab.className = 'flex-1 py-2 text-xs font-bold rounded-xl bg-white text-slate-900 shadow-sm transition';
    loginTab.className = 'flex-1 py-2 text-xs font-bold rounded-xl text-slate-500 hover:text-slate-800 transition';
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value.trim();
  const errorBox = document.getElementById('auth-error');
  const submitBtn = e.target.querySelector('button[type="submit"]');

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in…';
  }
  if (errorBox) errorBox.classList.add('hidden');

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (res.ok && data.token) {
      state.authToken = data.token;
      state.currentUser = data.user;
      localStorage.setItem('SPLITKART_token', data.token);
      localStorage.setItem('SPLITKART_user', JSON.stringify(data.user));
      showToast(`Welcome back, ${data.user.name}! 👋`, 'success');
      await afterLogin();
    } else {
      if (errorBox) {
        errorBox.textContent = data.error || 'Invalid email or password.';
        errorBox.classList.remove('hidden');
      }
    }
  } catch (err) {
    console.error('Login error:', err);
    if (errorBox) {
      errorBox.textContent = 'Server is waking up — please try again in a moment.';
      errorBox.classList.remove('hidden');
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Sign In';
    }
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById('reg-name').value.trim();
  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value.trim();
  const errorBox = document.getElementById('auth-error');
  const submitBtn = e.target.querySelector('button[type="submit"]');

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating account…';
  }
  if (errorBox) errorBox.classList.add('hidden');

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, username, password })
    });
    const data = await res.json();

    if (res.ok && data.token) {
      state.authToken = data.token;
      state.currentUser = data.user;
      localStorage.setItem('SPLITKART_token', data.token);
      localStorage.setItem('SPLITKART_user', JSON.stringify(data.user));
      showToast(`Welcome to SPLITKART, ${data.user.name}! 🛒`, 'success');
      await afterLogin();
    } else {
      if (errorBox) {
        errorBox.textContent = data.error || 'Registration failed.';
        errorBox.classList.remove('hidden');
      }
    }
  } catch (err) {
    console.error('Registration error:', err);
    if (errorBox) {
      errorBox.textContent = 'Server is waking up — please try again in a moment.';
      errorBox.classList.remove('hidden');
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create Account';
    }
  }
}

// Called after successful login/register — immediately enter the app
async function afterLogin() {
  showAppScreen();
  await loadState();
}

async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: getAuthHeaders()
    });
  } catch (e) {}

  state.authToken = null;
  state.currentUser = null;
  state.activeGroupId = null;
  state.activeGroup = null;
  localStorage.removeItem('SPLITKART_token');
  localStorage.removeItem('SPLITKART_user');
  localStorage.removeItem('splitkart_group_id');
  localStorage.removeItem('splitkart_group');
  localStorage.removeItem('palacharak_token');
  localStorage.removeItem('palacharak_user');
  localStorage.removeItem('palachrakk_token');
  localStorage.removeItem('cartshare_token');
  showAuthScreen();
  showToast('Logged out successfully.', 'info');
}

function showAuthScreen() {
  document.getElementById('auth-screen').classList.remove('hidden');
  document.getElementById('auth-screen').classList.add('flex');
  document.getElementById('app-screen').classList.add('hidden');
  document.getElementById('app-screen').classList.remove('flex');
}

function showAppScreen() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('auth-screen').classList.remove('flex');
  document.getElementById('app-screen').classList.remove('hidden');
  document.getElementById('app-screen').classList.add('flex');
}

// =========================================================
// 2. GROUPS MANAGEMENT (Switch, Create, Join)
// =========================================================

async function openGroupModal() {
  openModal('group-modal');
  await loadGroupsForSelector();
}

async function loadGroupsForSelector() {
  const listEl = document.getElementById('group-modal-list');
  const countBadge = document.getElementById('group-count-badge');
  if (listEl) listEl.innerHTML = '<p class="text-xs text-slate-400 text-center py-3">Loading groups…</p>';

  try {
    const res = await fetch('/api/groups', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    state.availableGroups = data.groups || [];
    if (countBadge) countBadge.textContent = `${state.availableGroups.length} total`;
    renderGroupSelector(state.availableGroups);
  } catch (err) {
    console.error('Error loading groups:', err);
    if (listEl) listEl.innerHTML = '<p class="text-xs text-rose-500 text-center py-3">Could not load groups.</p>';
  }
}

function renderGroupSelector(groups) {
  const listEl = document.getElementById('group-modal-list');
  if (!listEl) return;

  if (!groups || groups.length === 0) {
    listEl.innerHTML = `
      <div class="text-center py-4 bg-slate-50 rounded-2xl border border-dashed border-slate-200">
        <p class="text-xs font-semibold text-slate-600">No shared groups yet</p>
        <p class="text-[11px] text-slate-400 mt-0.5">Create a group below or join with an invite code.</p>
      </div>
    `;
    return;
  }

  listEl.innerHTML = groups.map(g => {
    const isCurrent = state.activeGroupId === g.id;
    return `
      <div class="p-3 rounded-2xl border ${isCurrent ? 'border-emerald-500 bg-emerald-50/60 shadow-xs' : 'border-slate-200 bg-white hover:border-slate-300'} flex items-center justify-between gap-2 transition">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="font-bold text-slate-900 text-sm truncate">${escapeHtml(g.name)}</span>
            ${isCurrent ? '<span class="text-[9px] bg-emerald-600 text-white font-extrabold px-1.5 py-0.2 rounded-md">Active</span>' : ''}
          </div>
          <div class="text-[11px] text-slate-500 mt-0.5 flex items-center gap-1.5 flex-wrap">
            <span>Code: <strong class="font-mono text-emerald-700 font-bold">${escapeHtml(g.invite_code)}</strong></span>
            <button type="button" onclick="copyInviteCode('${escapeHtml(g.invite_code)}')" class="text-[10px] text-emerald-600 hover:underline font-bold">📋 Copy</button>
            <span class="text-slate-300">•</span>
            <span>${g.member_count} member${g.member_count !== 1 ? 's' : ''}</span>
          </div>
        </div>
        <button type="button" onclick="selectGroupById(${g.id})" class="px-3.5 py-1.5 rounded-xl ${isCurrent ? 'bg-emerald-600 text-white' : 'bg-slate-900 hover:bg-emerald-600 text-white'} text-xs font-bold transition flex-shrink-0">
          ${isCurrent ? 'Open' : 'Switch →'}
        </button>
      </div>
    `;
  }).join('');
}

function selectGroupById(groupId) {
  state.activeGroupId = groupId;
  localStorage.setItem('splitkart_group_id', String(groupId));
  closeModal('group-modal');
  loadState();

  if (groupId === 0) {
    showToast('Switched to Personal List (No Group)', 'info');
  } else {
    const grp = (state.availableGroups || []).find(g => g.id === groupId);
    showToast(grp ? `Opened "${grp.name}"` : 'Switched group', 'success');
  }
}

function copyInviteCode(code) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(code).then(() => {
      showToast(`Copied invite code: ${code}`, 'success');
    }).catch(() => {
      prompt('Share this invite code:', code);
    });
  } else {
    prompt('Share this invite code:', code);
  }
}

async function createGroup() {
  const nameInput = document.getElementById('new-group-name');
  const errorEl = document.getElementById('group-error');
  const name = nameInput ? nameInput.value.trim() : '';

  if (!name) {
    if (errorEl) { errorEl.textContent = 'Group name is required.'; errorEl.classList.remove('hidden'); }
    return;
  }
  if (errorEl) errorEl.classList.add('hidden');

  try {
    const res = await fetch('/api/groups/create', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (nameInput) nameInput.value = '';
      showToast(`Group "${data.group.name}" created! Code: ${data.group.invite_code}`, 'success');
      selectGroupById(data.group.id);
    } else {
      if (errorEl) { errorEl.textContent = data.error || 'Failed to create group.'; errorEl.classList.remove('hidden'); }
    }
  } catch (err) {
    if (errorEl) { errorEl.textContent = 'Network error.'; errorEl.classList.remove('hidden'); }
  }
}

async function joinGroup() {
  const codeInput = document.getElementById('join-group-code');
  const errorEl = document.getElementById('group-error');
  const code = codeInput ? codeInput.value.trim().toUpperCase() : '';

  if (!code) {
    if (errorEl) { errorEl.textContent = 'Please enter an invite code.'; errorEl.classList.remove('hidden'); }
    return;
  }
  if (errorEl) errorEl.classList.add('hidden');

  try {
    const res = await fetch('/api/groups/join', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ invite_code: code })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (codeInput) codeInput.value = '';
      showToast(`Joined "${data.group.name}"!`, 'success');
      selectGroupById(data.group.id);
    } else {
      if (errorEl) { errorEl.textContent = data.error || 'Invalid invite code.'; errorEl.classList.remove('hidden'); }
    }
  } catch (err) {
    if (errorEl) { errorEl.textContent = 'Network error.'; errorEl.classList.remove('hidden'); }
  }
}

// =========================================================
// 2B. MOBILE STATUS BAR NOTIFICATIONS (Service Worker)
// =========================================================

function checkPhoneNotificationStatus() {
  const banner = document.getElementById('notif-permission-banner');
  if ("Notification" in window) {
    if (Notification.permission === "granted") {
      state.notificationsEnabled = true;
      if (banner) banner.classList.add('hidden');
    } else if (Notification.permission === "default") {
      state.notificationsEnabled = false;
      if (banner) banner.classList.remove('hidden');
    } else {
      state.notificationsEnabled = false;
      if (banner) banner.classList.add('hidden');
    }
  }
}

async function requestPhoneNotificationPermission() {
  if (!("Notification" in window)) {
    showToast("Notifications not supported on this browser.", "warning");
    return;
  }

  const permission = await Notification.requestPermission();
  checkPhoneNotificationStatus();

  if (permission === "granted") {
    showToast("SPLITKART alerts enabled!", "success");
    await sendPhoneNotification(
      "SPLITKART Alerts Active! 🛒",
      "You will receive alerts in your status bar whenever friends add or buy items."
    );
  }
}

async function sendPhoneNotification(title, body) {
  if (!state.notificationsEnabled || !("Notification" in window) || Notification.permission !== "granted") {
    return;
  }

  const options = {
    body: body,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate: [200, 100, 200],
    tag: 'SPLITKART-' + Date.now(),
    renotify: true
  };

  if ('serviceWorker' in navigator) {
    try {
      const reg = await navigator.serviceWorker.ready;
      if (reg && reg.showNotification) {
        await reg.showNotification(title, options);
        return;
      }
    } catch (err) {}
  }

  try {
    new Notification(title, options);
  } catch (e) {}
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  const colors = {
    info: 'bg-slate-900 text-white border-slate-700',
    success: 'bg-emerald-600 text-white border-emerald-500',
    warning: 'bg-amber-600 text-white border-amber-500',
    purple: 'bg-purple-600 text-white border-purple-500'
  };

  toast.className = `toast-enter flex items-center gap-2.5 px-3.5 py-2.5 rounded-2xl shadow-lg text-xs font-semibold border ${colors[type] || colors.info} mb-2`;
  toast.innerHTML = `<span>${type === 'success' ? '✓' : type === 'purple' ? '🧾' : '🔔'}</span><span class="flex-1">${message}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Audio Synthesis
const audioCtx = (typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext))
  ? new (window.AudioContext || window.webkitAudioContext)()
  : null;

function playTone(freq, duration, type = 'sine', gainVal = 0.12) {
  if (!state.soundEnabled || !audioCtx) return;
  try {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(gainVal, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) {}
}

function playSound(type) {
  if (!state.soundEnabled) return;
  if (type === 'buy') {
    playTone(523.25, 0.1);
    setTimeout(() => playTone(659.25, 0.16), 80);
  } else if (type === 'add') {
    playTone(587.33, 0.12);
  } else if (type === 'bill') {
    playTone(440.0, 0.08);
    setTimeout(() => playTone(554.37, 0.08), 60);
    setTimeout(() => playTone(659.25, 0.14), 120);
  } else if (type === 'settle') {
    playTone(659.25, 0.1);
    setTimeout(() => playTone(880.0, 0.18), 90);
  } else if (type === 'clear') {
    playTone(440.0, 0.08);
    setTimeout(() => playTone(349.23, 0.12), 70);
  }
}

function toggleAudio() {
  state.soundEnabled = !state.soundEnabled;
  const btn = document.getElementById('sound-toggle-btn');
  if (btn) btn.innerHTML = state.soundEnabled ? '🔊' : '🔇';
  showToast(state.soundEnabled ? "Audio enabled" : "Audio muted", "info");
}

// =========================================================
// 3. REAL-TIME SERVER-SENT EVENTS (SSE)
// =========================================================

function connectSSE() {
  const liveIndicator = document.getElementById('live-indicator');
  const es = new EventSource('/api/events');

  es.onopen = () => {
    state.isConnected = true;
    if (liveIndicator) liveIndicator.className = 'w-2 h-2 rounded-full bg-emerald-500 pulse-live';
  };

  es.addEventListener('state_updated', (e) => {
    try {
      const data = JSON.parse(e.data);
      handleLiveEvent(data);
      loadState(false);
    } catch (err) {}
  });

  es.onerror = () => {
    state.isConnected = false;
    if (liveIndicator) liveIndicator.className = 'w-2 h-2 rounded-full bg-rose-500';
  };
}

function handleLiveEvent(data) {
  const isMe = state.currentUser && state.currentUser.id === data.actor_id;

  if (data.action === 'item_added') {
    if (!isMe) {
      sendPhoneNotification("🛒 SPLITKART: New Item", `${data.actor || 'A friend'} added "${data.title}"`);
      playSound('add');
    }
    showToast(`${data.actor || 'Someone'} added: ${data.title}`, 'info');
  } else if (data.action === 'item_merged') {
    if (!isMe) {
      sendPhoneNotification("🛒 SPLITKART: Item Updated", `${data.actor || 'A friend'} added more to "${data.title}" (Now ${data.quantity})`);
      playSound('add');
    }
    showToast(`${data.actor || 'Someone'} added more to "${data.title}" (Total: ${data.quantity})`, 'info');
  } else if (data.action === 'item_toggled') {
    if (data.is_bought) {
      if (!isMe) {
        sendPhoneNotification("✓ SPLITKART: Item Bought", `${data.actor || 'A friend'} bought "${data.title}"`);
        playSound('buy');
      }
      showToast(`${data.actor || 'Someone'} bought: ${data.title}`, 'success');
    }
  } else if (data.action === 'bill_added') {
    if (!isMe) {
      sendPhoneNotification("🧾 SPLITKART: New Bill (€)", `${data.payer} added €${Number(data.amount).toFixed(2)} bill`);
      playSound('bill');
    }
    showToast(`${data.payer} added €${Number(data.amount).toFixed(2)} bill for ${data.store}!`, 'purple');
  } else if (data.action === 'settlement') {
    if (!isMe) {
      sendPhoneNotification("💶 SPLITKART: Debt Settled", `${data.from} paid €${Number(data.amount).toFixed(2)} to ${data.to}`);
      playSound('settle');
    }
    showToast(`${data.from} paid €${Number(data.amount).toFixed(2)} to ${data.to}`, 'success');
  } else if (data.action === 'member_removed') {
    showToast(`Member removed: ${data.name}`, 'info');
  }
}

// =========================================================
// 4. FETCH APPLICATION DATA
// =========================================================

let _loadStateRetries = 0;
const _MAX_RETRIES = 20;

async function loadState(initial = false) {
  const gidParam = (state.activeGroupId !== null && state.activeGroupId !== undefined) ? state.activeGroupId : '';

  try {
    const res = await fetch(`/api/state?group_id=${gidParam}`, { headers: getAuthHeaders() });

    if (res.status === 401) {
      const cachedUser = localStorage.getItem('SPLITKART_user') || localStorage.getItem('palacharak_user');
      if (!cachedUser && !state.currentUser) {
        showAuthScreen();
      } else {
        scheduleLoadStateRetry();
      }
      return;
    }

    const data = await res.json();
    _loadStateRetries = 0;

    state.currentUser = data.currentUser || state.currentUser;
    state.activeGroup = data.active_group || data.group || null;
    if (state.activeGroup && state.activeGroup.id !== undefined) {
      state.activeGroupId = state.activeGroup.id;
      localStorage.setItem('splitkart_group_id', String(state.activeGroup.id));
    }
    state.availableGroups = data.groups || [];
    state.members = data.members || [];
    state.activeItems = data.active_items || [];
    state.boughtItems = data.bought_items || [];
    state.bills = data.bills || [];
    state.balances = data.balances || [];
    state.transfers = data.transfers || [];
    state.activities = data.activities || [];
    state.stats = data.stats || {};

    if (state.currentUser) {
      localStorage.setItem('SPLITKART_user', JSON.stringify(state.currentUser));
      showAppScreen();
      renderLockedUserProfile();
      renderGroupBadge();
      renderGroceryList();
      renderBillsAndSplits();
      renderFriendsDirectory();
      checkPhoneNotificationStatus();
    } else {
      const cachedUser = localStorage.getItem('SPLITKART_user') || localStorage.getItem('palacharak_user');
      if (!cachedUser) {
        showAuthScreen();
      } else {
        scheduleLoadStateRetry();
      }
    }
  } catch (err) {
    console.warn('loadState network error:', err.message);
    scheduleLoadStateRetry();
  }
}

function scheduleLoadStateRetry() {
  if (_loadStateRetries >= _MAX_RETRIES) {
    const cachedUser = localStorage.getItem('SPLITKART_user');
    if (cachedUser) {
      showToast('Server unreachable. Working offline.', 'warning');
    } else {
      showAuthScreen();
    }
    _loadStateRetries = 0;
    return;
  }
  _loadStateRetries++;
  const delayMs = _loadStateRetries === 1 ? 3000 : 5000;
  if (_loadStateRetries <= 2) {
    showToast('Connecting to server…', 'info');
  }
  setTimeout(() => loadState(false), delayMs);
}

// =========================================================
// 5. RENDERERS
// =========================================================

function renderLockedUserProfile() {
  const pill = document.getElementById('user-profile-pill');
  if (!state.currentUser || !pill) return;

  const isAdmin = isUserAdmin();
  pill.innerHTML = `
    <div class="flex items-center gap-1.5 bg-slate-100/90 rounded-xl px-2 py-1">
      <span class="w-5 h-5 rounded-lg flex items-center justify-center text-white text-[10px] font-bold" style="background-color: ${state.currentUser.avatar_color || '#10b981'}">
        ${(state.currentUser.name || 'U')[0].toUpperCase()}
      </span>
      <span class="text-xs font-bold text-slate-800">${escapeHtml(state.currentUser.name)}</span>
      ${isAdmin ? '<span class="text-[9px] bg-amber-100 text-amber-800 font-extrabold px-1.5 py-0.2 rounded-md">Admin</span>' : ''}
      <button onclick="logout()" class="ml-1 text-slate-400 hover:text-rose-600 text-xs font-bold" title="Log Out">✕</button>
    </div>
  `;

  const groceryBadge = document.getElementById('tab-grocery-badge');
  if (groceryBadge) {
    groceryBadge.textContent = state.activeItems.length;
  }
}

function renderGroupBadge() {
  const isPersonal = !state.activeGroup || state.activeGroup.id === 0;
  const name = isPersonal ? 'Personal List (No Group)' : state.activeGroup.name;
  const code = isPersonal ? '' : (state.activeGroup.invite_code || '');

  // Header button text
  const badgeEl = document.getElementById('header-group-name');
  if (badgeEl) {
    badgeEl.textContent = isPersonal ? 'Personal List' : state.activeGroup.name;
  }

  // Friends tab group card
  const friendsName = document.getElementById('friends-tab-group-name');
  const friendsCode = document.getElementById('friends-tab-invite-code');
  const inviteBox = document.getElementById('friends-tab-invite-box');

  if (friendsName) friendsName.textContent = name;
  if (friendsCode) friendsCode.textContent = code || '------';
  if (inviteBox) {
    inviteBox.style.display = isPersonal ? 'none' : 'flex';
  }
}

function copyActiveGroupInviteCode() {
  if (state.activeGroup && state.activeGroup.invite_code) {
    copyInviteCode(state.activeGroup.invite_code);
  } else {
    openGroupModal();
  }
}

function renderGroceryList() {
  const container = document.getElementById('grocery-items-container');
  const boughtContainer = document.getElementById('bought-items-container');
  const boughtCountSpan = document.getElementById('bought-count-badge');
  const clearBoughtBtn = document.getElementById('clear-bought-btn');

  if (!container) return;

  let filtered = state.activeItems.filter(item => {
    const matchesCat = state.selectedCategory === 'All' || item.category === state.selectedCategory;
    return matchesCat;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="text-center py-10 bg-white rounded-2xl border border-dashed border-slate-200">
        <div class="text-3xl mb-1">🛒</div>
        <div class="text-slate-800 font-bold text-sm">Grocery list is clear!</div>
        <p class="text-slate-400 text-xs mt-0.5">Use the box above to add what you need from the supermarket.</p>
      </div>
    `;
  } else {
    container.innerHTML = filtered.map(item => `
      <div class="bg-white rounded-2xl p-3 border border-slate-100 shadow-xs flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <input type="checkbox"
                 class="custom-checkbox flex-shrink-0"
                 onchange="openBuyModal(${item.id}, '${escapeHtml(item.quantity)}')"
                 title="Mark as bought" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-slate-900 text-sm truncate">${escapeHtml(item.title)}</span>
              <span class="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md">${escapeHtml(item.quantity)}</span>
            </div>
            <div class="flex items-center gap-2 mt-1 text-[11px] text-slate-400 flex-wrap">
              <span>By <strong class="text-slate-600">${escapeHtml(item.added_by_name || 'Group')}</strong></span>
              ${item.created_at ? `<span>• 🕒 ${formatDateTime(item.created_at)}</span>` : ''}
            </div>
          </div>
        </div>
        <button onclick="deleteItem(${item.id})" class="text-slate-300 hover:text-rose-500 p-1.5" title="Delete">✕</button>
      </div>
    `).join('');
  }

  if (boughtCountSpan) boughtCountSpan.textContent = state.boughtItems.length;
  if (clearBoughtBtn) {
    clearBoughtBtn.style.display = state.boughtItems.length > 0 ? 'inline-flex' : 'none';
  }

  if (boughtContainer) {
    if (state.boughtItems.length === 0) {
      boughtContainer.innerHTML = `<p class="text-xs text-slate-400 py-2 text-center italic">Purchased items will appear here.</p>`;
    } else {
      boughtContainer.innerHTML = state.boughtItems.map(item => `
        <div class="flex items-center justify-between p-2 rounded-xl bg-slate-50 border border-slate-100 text-xs">
          <div class="flex items-center gap-2 min-w-0">
            <button onclick="toggleItemBought(${item.id})" class="w-5 h-5 rounded-md bg-emerald-600 text-white flex items-center justify-center text-[10px] font-bold" title="Put back to cart">✓</button>
            <div class="min-w-0">
              <span class="line-through text-slate-400 font-medium">${escapeHtml(item.title)}</span>
              <span class="ml-1 text-emerald-700 font-bold no-underline" style="text-decoration:none">${escapeHtml(item.purchased_qty || item.quantity)}</span>
              <div class="text-[10px] text-slate-400">
                Bought by <strong class="text-slate-600">${escapeHtml(item.bought_by_name || 'Someone')}</strong>
                ${item.bought_at ? `• 🕒 ${formatDateTime(item.bought_at)}` : ''}
              </div>
            </div>
          </div>
          <button onclick="deleteItem(${item.id})" class="text-slate-300 hover:text-rose-500 p-1" title="Remove">✕</button>
        </div>
      `).join('');
    }
  }

  renderCategoryPills();
}

function renderCategoryPills() {
  const container = document.getElementById('category-pills');
  if (!container) return;

  const categories = ['All', 'Produce', 'Dairy', 'Bakery', 'Pantry', 'Snacks', 'Drinks', 'Meat', 'Other'];
  container.innerHTML = categories.map(cat => {
    const isSelected = state.selectedCategory === cat;
    return `
      <button onclick="selectCategory('${cat}')"
              class="flex-shrink-0 px-3 py-1 rounded-xl text-xs font-bold transition ${
                isSelected
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-600 border border-slate-200/80 hover:bg-slate-100'
              }">
        ${cat}
      </button>
    `;
  }).join('');
}

function renderBillsAndSplits() {
  const myBalanceEl = document.getElementById('stat-my-balance');
  const myBalanceLabel = document.getElementById('stat-my-balance-label');

  const myBalObj = state.balances.find(b => b.id === (state.currentUser ? state.currentUser.id : null));
  const myBal = myBalObj ? myBalObj.balance : 0.0;

  if (myBalanceEl) {
    if (myBal > 0.01) {
      myBalanceEl.textContent = `+€${myBal.toFixed(2)}`;
      myBalanceEl.className = 'text-2xl font-black text-emerald-600';
      if (myBalanceLabel) myBalanceLabel.textContent = 'You are owed by friends';
    } else if (myBal < -0.01) {
      myBalanceEl.textContent = `-€${Math.abs(myBal).toFixed(2)}`;
      myBalanceEl.className = 'text-2xl font-black text-rose-600';
      if (myBalanceLabel) myBalanceLabel.textContent = 'You owe the group';
    } else {
      myBalanceEl.textContent = '€0.00';
      myBalanceEl.className = 'text-2xl font-black text-slate-800';
      if (myBalanceLabel) myBalanceLabel.textContent = 'All settled up';
    }
  }

  const transfersContainer = document.getElementById('transfers-container');
  if (transfersContainer) {
    if (state.transfers.length === 0) {
      transfersContainer.innerHTML = `
        <div class="p-4 text-center bg-emerald-50/60 rounded-2xl border border-emerald-100">
          <div class="text-sm font-bold text-emerald-800">🎉 Everyone is squared away! No outstanding debts.</div>
        </div>
      `;
    } else {
      transfersContainer.innerHTML = state.transfers.map(t => {
        const isMeFrom = state.currentUser && t.from_id === state.currentUser.id;
        return `
          <div class="p-3.5 rounded-2xl bg-white border border-slate-100 shadow-xs flex items-center justify-between gap-3">
            <div>
              <div class="text-xs text-slate-500 font-medium">
                <strong class="text-slate-800 font-bold">${escapeHtml(t.from_name)}</strong> owes <strong class="text-slate-800 font-bold">${escapeHtml(t.to_name)}</strong>
              </div>
              <div class="text-base font-black text-slate-900 mt-0.5">€${Number(t.amount).toFixed(2)}</div>
            </div>
            ${isMeFrom ? `
              <button onclick="openSettleModal(${t.to_id}, '${escapeHtml(t.to_name)}', ${t.amount})"
                      class="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-emerald-600 text-white font-bold text-xs transition">
                Pay Back ✓
              </button>
            ` : ''}
          </div>
        `;
      }).join('');
    }
  }

  const balancesContainer = document.getElementById('member-balances-container');
  if (balancesContainer) {
    balancesContainer.innerHTML = state.balances.map(m => {
      const isPositive = m.balance > 0.01;
      const isNegative = m.balance < -0.01;
      const isMe = state.currentUser && m.id === state.currentUser.id;
      return `
        <div class="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0 text-xs">
          <span class="font-bold text-slate-700">${escapeHtml(m.name)} ${isMe ? '(You)' : ''}</span>
          <span class="font-black ${isPositive ? 'text-emerald-600' : isNegative ? 'text-rose-600' : 'text-slate-400'}">
            ${isPositive ? '+' : ''}€${m.balance.toFixed(2)}
          </span>
        </div>
      `;
    }).join('');
  }

  const billsContainer = document.getElementById('bills-list-container');
  if (billsContainer) {
    if (state.bills.length === 0) {
      billsContainer.innerHTML = `<div class="text-center py-4 text-xs text-slate-400">No bills added yet.</div>`;
    } else {
      billsContainer.innerHTML = state.bills.map(b => `
        <div class="p-3 rounded-2xl bg-white border border-slate-100 shadow-xs flex items-center justify-between">
          <div>
            <div class="font-bold text-slate-800 text-xs">🛒 ${escapeHtml(b.store_name)}</div>
            <div class="text-[11px] text-slate-400">Paid by ${escapeHtml(b.paid_by_name)} • ${escapeHtml(b.bill_date)}</div>
          </div>
          <div class="text-right">
            <div class="text-sm font-black text-slate-900">€${Number(b.total_amount).toFixed(2)}</div>
            <div class="text-[10px] text-slate-400">Split by ${b.splits.length}</div>
          </div>
        </div>
      `).join('');
    }
  }
}

// =========================================================
// 5B. FRIENDS DIRECTORY & WORKING ADMIN REMOVE
// =========================================================

function renderFriendsDirectory() {
  const container = document.getElementById('friends-list-container');
  const summaryEl = document.getElementById('stat-friends-summary');
  const onlineBadgeEl = document.getElementById('tab-online-badge');

  const onlineCount = state.members.filter(m => m.is_online).length;
  if (summaryEl) summaryEl.textContent = `${state.members.length} members • ${onlineCount} online`;
  if (onlineBadgeEl) onlineBadgeEl.textContent = `${onlineCount} Online`;

  if (!container) return;

  const isAdmin = isUserAdmin();

  container.innerHTML = state.members.map(m => {
    const isMe = state.currentUser && m.id === state.currentUser.id;
    return `
      <div class="bg-white rounded-2xl p-3.5 border border-slate-100 shadow-xs flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <div class="relative">
            <span class="w-9 h-9 rounded-xl flex items-center justify-center text-white text-xs font-bold" style="background-color: ${m.avatar_color || '#10b981'}">
              ${m.name[0].toUpperCase()}
            </span>
            <span class="w-2.5 h-2.5 rounded-full absolute -bottom-0.5 -right-0.5 border-2 border-white ${m.is_online ? 'bg-emerald-500 pulse-live' : 'bg-slate-300'}"></span>
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="font-bold text-slate-800 text-sm truncate">${escapeHtml(m.name)}</span>
              ${m.is_admin ? '<span class="text-[9px] bg-amber-100 text-amber-800 font-extrabold px-1.5 py-0.2 rounded-md">Admin</span>' : ''}
              ${isMe ? '<span class="text-[9px] bg-emerald-50 text-emerald-700 font-extrabold px-1.5 py-0.2 rounded-md">You</span>' : ''}
            </div>
            <div class="text-[11px] text-slate-400 mt-0.5">
              ${m.is_online
                ? '<strong class="text-emerald-600 font-semibold">Online now</strong>'
                : (m.last_login ? `Last login: ${formatDateTime(m.last_login)}` : 'Offline')}
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          ${isAdmin && !isMe ? `
            <button type="button" onclick="removeMember(${m.id})"
                    class="px-2.5 py-1 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold transition flex items-center gap-1 shadow-2xs"
                    title="Remove candidate">
              <span>Remove</span>
              <span>✕</span>
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');

  const actContainer = document.getElementById('activity-list-container');
  if (actContainer) {
    if (state.activities.length === 0) {
      actContainer.innerHTML = `<div class="text-center py-3 text-xs text-slate-400">No activity yet.</div>`;
    } else {
      actContainer.innerHTML = state.activities.slice(0, 15).map(a => `
        <div class="p-2.5 rounded-xl bg-white border border-slate-100 text-xs flex items-center justify-between gap-2">
          <span class="text-slate-700 font-medium">${escapeHtml(a.message)}</span>
          <span class="text-[10px] text-slate-400 flex-shrink-0">${formatDateTime(a.created_at)}</span>
        </div>
      `).join('');
    }
  }
}

async function removeMember(memberId) {
  const member = (state.members || []).find(m => m.id === memberId);
  const memberName = member ? member.name : 'this candidate';
  if (!confirm(`Are you sure you want to remove "${memberName}" from SPLITKART?`)) return;

  try {
    const res = await fetch('/api/members/remove', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ member_id: memberId })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(`Removed ${memberName}`, 'info');
      await loadState();
    } else {
      alert(data.error || 'Failed to remove member.');
    }
  } catch (err) {
    console.error('Error removing member:', err);
    alert('Network error removing member.');
  }
}

// =========================================================
// 6. USER ACTIONS
// =========================================================

async function addItem(e) {
  e.preventDefault();
  const titleInput = document.getElementById('item-title-input');
  const qtyInput = document.getElementById('item-qty-input');
  const catInput = document.getElementById('item-cat-input');

  const title = titleInput.value.trim();
  const quantity = qtyInput.value.trim() || '1';
  const category = catInput.value;

  if (!title) return;

  // 1. Check if an item with the same name is already on the active checklist
  const existingItem = state.activeItems.find(
    item => item.title.trim().toLowerCase() === title.toLowerCase()
  );

  if (existingItem) {
    const adder = existingItem.added_by_name || 'Someone';
    const currentQty = existingItem.quantity || '1';

    // Notify candidate that item is already there and ask if they want to add it again
    const promptMsg = `"${existingItem.title}" is already on the grocery list!\n` +
                      `Current quantity: ${currentQty} (added by ${adder}).\n\n` +
                      `Do you want to add ${quantity} more to it?`;

    if (!confirm(promptMsg)) {
      return; // Cancelled by candidate
    }

    // Merge into the 1 individual item
    try {
      const res = await fetch('/api/items/merge', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          item_id: existingItem.id,
          add_quantity: quantity
        })
      });

      if (res.ok) {
        const data = await res.json();
        titleInput.value = '';
        qtyInput.value = '';
        titleInput.focus();
        playSound('add');
        showToast(`Combined with "${existingItem.title}" (Total: ${data.new_quantity})`, 'success');
        loadState();
      } else if (res.status === 401) {
        showAuthScreen();
      }
    } catch (err) {
      console.error("Failed to merge item:", err);
    }
    return;
  }

  // 2. Fresh new item
  try {
    const res = await fetch('/api/items', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ title, quantity, category, group_id: state.activeGroupId })
    });

    if (res.ok) {
      titleInput.value = '';
      qtyInput.value = '';
      titleInput.focus();
      playSound('add');
      loadState();
    } else if (res.status === 401) {
      showAuthScreen();
    }
  } catch (err) {
    console.error("Failed to add item:", err);
  }
}

function openBuyModal(itemId, currentQty) {
  document.getElementById('buy-item-id').value = itemId;
  const qtyInput = document.getElementById('buy-qty-input');
  if (qtyInput) qtyInput.value = currentQty || '1';
  openModal('buy-qty-modal');
  setTimeout(() => qtyInput && qtyInput.select(), 80);
}

async function confirmBuyItem() {
  const itemId = parseInt(document.getElementById('buy-item-id').value);
  const qty = document.getElementById('buy-qty-input').value.trim() || '1';

  closeModal('buy-qty-modal');

  try {
    const res = await fetch('/api/items/toggle', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ item_id: itemId, purchased_qty: qty })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.is_bought) playSound('buy');
      loadState();
    }
  } catch (err) {}
}

async function toggleItemBought(itemId) {
  const item = state.boughtItems.find(i => i.id === itemId);
  if (item) {
    try {
      const res = await fetch('/api/items/toggle', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ item_id: itemId })
      });
      if (res.ok) loadState();
    } catch (err) {}
  } else {
    const activeItem = state.activeItems.find(i => i.id === itemId);
    openBuyModal(itemId, activeItem ? activeItem.quantity : '1');
  }
}

async function deleteItem(itemId) {
  try {
    const res = await fetch('/api/items/delete', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ item_id: itemId })
    });
    if (res.ok) loadState();
  } catch (err) {}
}

async function clearBoughtItems() {
  if (!confirm("Clear all purchased items?")) return;
  try {
    const res = await fetch('/api/items/clear-bought', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ group_id: state.activeGroupId })
    });
    if (res.ok) {
      playSound('clear');
      loadState();
    }
  } catch (err) {}
}

async function submitBill(e) {
  e.preventDefault();
  const storeInput = document.getElementById('bill-store-input');
  const amountInput = document.getElementById('bill-amount-input');
  const payerInput = document.getElementById('bill-payer-select');
  const dateInput = document.getElementById('bill-date-input');

  const splitCheckboxes = document.querySelectorAll('.split-member-checkbox:checked');
  const splitWith = Array.from(splitCheckboxes).map(cb => parseInt(cb.value));

  const store = storeInput.value.trim() || 'Supermarket';
  const amount = parseFloat(amountInput.value);
  const paidBy = parseInt(payerInput.value);
  const date = dateInput.value;

  if (isNaN(amount) || amount <= 0) {
    showToast("Please enter a valid amount in Euros.", "warning");
    return;
  }
  if (splitWith.length === 0) {
    showToast("Please select at least one friend to split with.", "warning");
    return;
  }

  try {
    const res = await fetch('/api/bills', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        store_name: store,
        total_amount: amount,
        paid_by: paidBy,
        split_with: splitWith,
        bill_date: date,
        group_id: state.activeGroupId
      })
    });

    if (res.ok) {
      playSound('bill');
      closeModal('add-bill-modal');
      amountInput.value = '';
      storeInput.value = '';
      showToast(`Bill of €${amount.toFixed(2)} added!`, 'purple');
      loadState();
    }
  } catch (err) {}
}

async function submitSettlement(e) {
  e.preventDefault();
  const toId = parseInt(document.getElementById('settle-to-id').value);
  const amount = parseFloat(document.getElementById('settle-amount-input').value);

  if (isNaN(amount) || amount <= 0) return;

  try {
    const res = await fetch('/api/settlements', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ to_id: toId, amount: amount, group_id: state.activeGroupId })
    });
    if (res.ok) {
      playSound('settle');
      closeModal('settle-modal');
      showToast(`Payment of €${amount.toFixed(2)} recorded!`, "success");
      loadState();
    }
  } catch (err) {}
}

// Navigation Tabs
function switchTab(tabId) {
  state.activeTab = tabId;
  const tabs = ['grocery', 'bills', 'friends'];
  tabs.forEach(t => {
    const content = document.getElementById(`tab-content-${t}`);
    const btn = document.getElementById(`tab-btn-${t}`);
    if (content) content.style.display = (t === tabId) ? 'block' : 'none';
    if (btn) {
      if (t === tabId) {
        btn.className = 'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-2xl bg-slate-900 text-white font-bold text-xs shadow-sm transition';
      } else {
        btn.className = 'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-2xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-bold text-xs transition';
      }
    }
  });
}

function selectCategory(cat) {
  state.selectedCategory = cat;
  renderGroceryList();
}

// Modals
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

function openAddBillModal() {
  const payerSelect = document.getElementById('bill-payer-select');
  const splitCheckboxesContainer = document.getElementById('bill-split-members');
  const dateInput = document.getElementById('bill-date-input');

  if (dateInput) {
    dateInput.value = new Date().toISOString().split('T')[0];
  }

  if (payerSelect) {
    payerSelect.innerHTML = state.members.map(m => `
      <option value="${m.id}" ${state.currentUser && m.id === state.currentUser.id ? 'selected' : ''}>
        ${escapeHtml(m.name)} ${state.currentUser && m.id === state.currentUser.id ? '(You)' : ''}
      </option>
    `).join('');
  }

  if (splitCheckboxesContainer) {
    splitCheckboxesContainer.innerHTML = state.members.map(m => `
      <label class="flex items-center justify-between p-2 rounded-xl border border-slate-200 hover:bg-slate-50 cursor-pointer text-xs">
        <span class="font-semibold text-slate-700">${escapeHtml(m.name)}</span>
        <input type="checkbox" class="split-member-checkbox custom-checkbox" value="${m.id}" checked />
      </label>
    `).join('');
  }

  openModal('add-bill-modal');
}

function openSettleModal(toId, toName, amount) {
  const infoEl = document.getElementById('settle-modal-info');
  const amountInput = document.getElementById('settle-amount-input');
  document.getElementById('settle-to-id').value = toId;

  if (infoEl) {
    infoEl.innerHTML = `Paying <strong class="text-slate-800">${escapeHtml(toName)}</strong>`;
  }
  if (amountInput) {
    amountInput.value = amount.toFixed(2);
  }

  openModal('settle-modal');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDateTime(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr.replace(' ', 'T') + 'Z');
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short'
    }) + ', ' + d.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  } catch (e) {
    return dateStr;
  }
}

// PWA Install Prompt
let deferredPrompt = null;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
});

function triggerPwaInstall() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then((choiceResult) => {
      if (choiceResult.outcome === 'accepted') {
        showToast('SPLITKART app installed!', 'success');
      }
      deferredPrompt = null;
    });
  } else {
    openModal('install-guide-modal');
  }
}

// DOM Load
window.addEventListener('DOMContentLoaded', () => {
  const cachedToken = state.authToken;
  const cachedUserStr = localStorage.getItem('SPLITKART_user') || localStorage.getItem('palacharak_user');

  if (cachedToken && cachedUserStr) {
    try {
      const cachedUser = JSON.parse(cachedUserStr);
      state.currentUser = cachedUser;
      showAppScreen();
      renderLockedUserProfile();
      renderGroupBadge();
      loadState(true);
    } catch (e) {
      localStorage.removeItem('SPLITKART_user');
      localStorage.removeItem('palacharak_user');
      showAuthScreen();
    }
  } else if (cachedToken) {
    loadState(true);
  } else {
    showAuthScreen();
  }

  connectSSE();

  window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-backdrop')) {
      e.target.classList.add('hidden');
      e.target.classList.remove('flex');
    }
  });
});
