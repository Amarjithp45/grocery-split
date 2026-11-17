/**
 * CartShare Client Application
 * Real-time collaborative grocery checklist & expense splitting
 */

// Application State
const state = {
  currentMemberId: null,
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
  searchQuery: '',
  soundEnabled: true,
  notificationsEnabled: false,
  isConnected: false
};

// Web Audio API Sound Synthesizer (No external audio files needed!)
const audioCtx = (typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)) 
  ? new (window.AudioContext || window.webkitAudioContext)() 
  : null;

function playTone(freq, duration, type = 'sine', gainVal = 0.15) {
  if (!state.soundEnabled || !audioCtx) return;
  try {
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
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
  } catch (e) {
    console.warn("Audio playback error:", e);
  }
}

function playSound(type) {
  if (!state.soundEnabled) return;
  if (type === 'buy') {
    // Two-tone cheerful success chime
    playTone(523.25, 0.1, 'sine', 0.15); // C5
    setTimeout(() => playTone(659.25, 0.18, 'sine', 0.15), 90); // E5
  } else if (type === 'add') {
    playTone(587.33, 0.12, 'triangle', 0.12); // D5
  } else if (type === 'bill') {
    // Arpeggio
    playTone(440.0, 0.08, 'sine', 0.12);
    setTimeout(() => playTone(554.37, 0.08, 'sine', 0.12), 70);
    setTimeout(() => playTone(659.25, 0.16, 'sine', 0.14), 140);
  } else if (type === 'settle') {
    playTone(659.25, 0.1, 'sine', 0.15);
    setTimeout(() => playTone(880.0, 0.22, 'sine', 0.15), 100);
  } else if (type === 'clear') {
    playTone(440.0, 0.08, 'triangle', 0.1);
    setTimeout(() => playTone(349.23, 0.14, 'triangle', 0.1), 80);
  }
}

// Browser Push Notifications
function initBrowserNotifications() {
  if ("Notification" in window) {
    if (Notification.permission === "granted") {
      state.notificationsEnabled = true;
    }
    updateNotificationIcon();
  }
}

function toggleBrowserNotifications() {
  if (!("Notification" in window)) {
    showToast("Browser notifications not supported on this device.", "warning");
    return;
  }
  if (Notification.permission === "granted") {
    state.notificationsEnabled = !state.notificationsEnabled;
    showToast(state.notificationsEnabled ? "Notifications enabled" : "Notifications muted", "info");
    updateNotificationIcon();
  } else if (Notification.permission !== "denied") {
    Notification.requestPermission().then(permission => {
      if (permission === "granted") {
        state.notificationsEnabled = true;
        showToast("Notifications enabled!", "success");
        new Notification("CartShare", {
          body: "You will now get alerts when friends add items or supermarket bills!",
          icon: "🛒"
        });
      }
      updateNotificationIcon();
    });
  } else {
    showToast("Notifications blocked in browser settings.", "warning");
  }
}

function updateNotificationIcon() {
  const btn = document.getElementById("notif-toggle-btn");
  if (btn) {
    btn.className = `p-2 rounded-xl transition ${state.notificationsEnabled ? 'bg-emerald-100 text-emerald-700 font-medium' : 'text-slate-400 hover:text-slate-600'}`;
  }
}

function sendBrowserNotification(title, body) {
  if (state.notificationsEnabled && "Notification" in window && Notification.permission === "granted") {
    try {
      new Notification(title, { body, icon: "🛒" });
    } catch (e) {
      console.warn("Notification error:", e);
    }
  }
}

// In-app Toast Alerts
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

  toast.className = `toast-enter flex items-center gap-3 px-4 py-3 rounded-2xl shadow-xl text-sm font-medium border ${colors[type] || colors.info} mb-2.5`;
  toast.innerHTML = `
    <span class="text-base">${type === 'success' ? '✓' : type === 'purple' ? '🧾' : '🔔'}</span>
    <span class="flex-1">${message}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Server-Sent Events (SSE) Real-Time Connection
function connectSSE() {
  const liveIndicator = document.getElementById('live-indicator');
  const liveText = document.getElementById('live-text');

  const es = new EventSource('/api/events');

  es.onopen = () => {
    state.isConnected = true;
    if (liveIndicator) liveIndicator.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 pulse-live';
    if (liveText) liveText.textContent = 'Live Sync';
  };

  es.addEventListener('state_updated', (e) => {
    try {
      const data = JSON.parse(e.data);
      handleLiveEvent(data);
      loadState(false); // silent refresh
    } catch (err) {
      console.error("SSE parse error", err);
    }
  });

  es.onerror = () => {
    state.isConnected = false;
    if (liveIndicator) liveIndicator.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
    if (liveText) liveText.textContent = 'Reconnecting...';
  };
}

function handleLiveEvent(data) {
  if (data.action === 'item_added') {
    showToast(`${data.added_by || 'Someone'} added: ${data.title}`, 'info');
    sendBrowserNotification("CartShare: New Grocery Item", `${data.added_by || 'Someone'} added "${data.title}"`);
    playSound('add');
  } else if (data.action === 'item_toggled') {
    if (data.is_bought) {
      showToast(`${data.actor || 'Someone'} bought: ${data.title}`, 'success');
      sendBrowserNotification("CartShare: Item Bought", `${data.actor || 'Someone'} bought "${data.title}"!`);
      playSound('buy');
    }
  } else if (data.action === 'bill_added') {
    showToast(`${data.payer} added a $${Number(data.amount).toFixed(2)} bill for ${data.store}!`, 'purple');
    sendBrowserNotification("CartShare: New Bill Added", `${data.payer} added a $${Number(data.amount).toFixed(2)} bill for ${data.store}`);
    playSound('bill');
  } else if (data.action === 'settlement') {
    showToast(`${data.from} paid $${Number(data.amount).toFixed(2)} to ${data.to} (Settled)`, 'success');
    playSound('settle');
  } else if (data.action === 'cleared_bought') {
    showToast(`${data.actor} cleared purchased items`, 'info');
    playSound('clear');
  }
}

// Fetch Full Application State
async function loadState(showLoading = false) {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();

    state.members = data.members || [];
    state.activeItems = data.active_items || [];
    state.boughtItems = data.bought_items || [];
    state.bills = data.bills || [];
    state.balances = data.balances || [];
    state.transfers = data.transfers || [];
    state.activities = data.activities || [];
    state.stats = data.stats || {};

    // Restore or set current member
    const savedMemberId = localStorage.getItem('cartshare_member_id');
    if (savedMemberId && state.members.some(m => m.id == savedMemberId)) {
      state.currentMemberId = parseInt(savedMemberId);
    } else if (state.members.length > 0 && !state.currentMemberId) {
      state.currentMemberId = state.members[0].id;
      localStorage.setItem('cartshare_member_id', state.currentMemberId);
    }

    renderHeader();
    renderGroceryList();
    renderBillsAndSplits();
    renderActivityFeed();
  } catch (err) {
    console.error("Failed to load state:", err);
  }
}

// UI Renderers
function renderHeader() {
  const memberSelect = document.getElementById('current-member-badge');
  const currentMember = state.members.find(m => m.id === state.currentMemberId);

  if (memberSelect && currentMember) {
    memberSelect.innerHTML = `
      <div class="flex items-center gap-2 cursor-pointer bg-white/90 border border-slate-200/80 rounded-2xl px-3 py-1.5 shadow-sm hover:border-emerald-500 transition" onclick="openMemberModal()">
        <span class="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shadow-sm" style="background-color: ${currentMember.avatar_color}">
          ${currentMember.name[0].toUpperCase()}
        </span>
        <div class="text-left leading-tight hidden sm:block">
          <div class="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Shopping as</div>
          <div class="text-xs font-bold text-slate-800">${currentMember.name}</div>
        </div>
        <svg class="w-3.5 h-3.5 text-slate-400 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"></path></svg>
      </div>
    `;
  }

  // Grocery count badge
  const groceryBadge = document.getElementById('tab-grocery-badge');
  if (groceryBadge) {
    groceryBadge.textContent = state.activeItems.length;
    groceryBadge.className = `ml-1.5 px-2 py-0.5 text-xs rounded-full font-bold ${state.activeItems.length > 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`;
  }

  // Sound toggle button icon
  const soundBtn = document.getElementById('sound-toggle-btn');
  if (soundBtn) {
    soundBtn.innerHTML = state.soundEnabled ? '🔊' : '🔇';
    soundBtn.title = state.soundEnabled ? 'Audio chimes active (Click to mute)' : 'Muted (Click to enable)';
  }
}

function renderGroceryList() {
  const container = document.getElementById('grocery-items-container');
  const boughtContainer = document.getElementById('bought-items-container');
  const boughtCountSpan = document.getElementById('bought-count-badge');
  const clearBoughtBtn = document.getElementById('clear-bought-btn');

  if (!container) return;

  // Filter items
  let filtered = state.activeItems.filter(item => {
    const matchesCat = state.selectedCategory === 'All' || item.category === state.selectedCategory;
    const matchesSearch = !state.searchQuery || item.title.toLowerCase().includes(state.searchQuery.toLowerCase());
    return matchesCat && matchesSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="text-center py-14 bg-white/70 rounded-3xl border border-dashed border-slate-200">
        <div class="text-5xl mb-3">🛒</div>
        <h3 class="text-slate-800 font-bold text-base">All clear in this section!</h3>
        <p class="text-slate-500 text-xs mt-1 max-w-xs mx-auto">No items in the grocery list. Use the quick add bar above to add what you need from the supermarket.</p>
      </div>
    `;
  } else {
    container.innerHTML = filtered.map(item => `
      <div class="group bg-white rounded-2xl p-3.5 border border-slate-100 shadow-sm hover:shadow-md transition flex items-center justify-between gap-3 animate-slide-down">
        <div class="flex items-center gap-3.5 min-w-0 flex-1">
          <input type="checkbox" 
                 class="custom-checkbox flex-shrink-0" 
                 onchange="toggleItemBought(${item.id})"
                 title="Mark as bought" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-slate-800 text-sm tracking-tight truncate">${escapeHtml(item.title)}</span>
              ${item.is_urgent ? '<span class="bg-rose-100 text-rose-700 text-[10px] font-extrabold px-2 py-0.5 rounded-full border border-rose-200">★ URGENT</span>' : ''}
              <span class="badge-${item.category} text-[10px] font-bold px-2 py-0.5 rounded-lg">${item.category}</span>
            </div>
            <div class="flex items-center gap-2 mt-1 text-xs text-slate-400">
              <span class="font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100/60">${escapeHtml(item.quantity)}</span>
              <span>•</span>
              <span class="flex items-center gap-1">
                <span class="w-2 h-2 rounded-full inline-block" style="background-color: ${item.added_by_color || '#94a3b8'}"></span>
                ${escapeHtml(item.added_by_name || 'Group')}
              </span>
            </div>
          </div>
        </div>
        <button onclick="deleteItem(${item.id})" class="text-slate-300 hover:text-rose-500 p-2 rounded-xl hover:bg-rose-50 transition" title="Delete item">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
        </button>
      </div>
    `).join('');
  }

  // Bought items tray
  if (boughtCountSpan) boughtCountSpan.textContent = state.boughtItems.length;
  if (clearBoughtBtn) {
    clearBoughtBtn.style.display = state.boughtItems.length > 0 ? 'inline-flex' : 'none';
  }

  if (boughtContainer) {
    if (state.boughtItems.length === 0) {
      boughtContainer.innerHTML = `<p class="text-xs text-slate-400 py-3 text-center italic">Items marked as bought at the supermarket will show up here.</p>`;
    } else {
      boughtContainer.innerHTML = state.boughtItems.map(item => `
        <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 border border-slate-100 text-xs">
          <div class="flex items-center gap-2.5 min-w-0">
            <button onclick="toggleItemBought(${item.id})" class="w-6 h-6 rounded-lg bg-emerald-600 text-white flex items-center justify-center text-xs font-bold hover:bg-emerald-700 transition" title="Move back to active cart">
              ✓
            </button>
            <div class="min-w-0">
              <span class="line-through text-slate-400 font-medium">${escapeHtml(item.title)}</span>
              <span class="text-slate-400 text-[11px] ml-1.5">(${escapeHtml(item.quantity)})</span>
              <div class="text-[10px] text-slate-400">Bought by <strong class="text-slate-600">${escapeHtml(item.bought_by_name || 'Someone')}</strong></div>
            </div>
          </div>
          <button onclick="deleteItem(${item.id})" class="text-slate-300 hover:text-rose-500 p-1.5" title="Remove permanently">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>
      `).join('');
    }
  }

  renderCategoryPills();
}

function renderCategoryPills() {
  const container = document.getElementById('category-pills');
  if (!container) return;

  const categories = ['All', 'Produce', 'Dairy', 'Bakery', 'Pantry', 'Snacks', 'Drinks', 'Household', 'Frozen', 'Meat', 'Other'];
  
  // Count per category
  const counts = { All: state.activeItems.length };
  for (const item of state.activeItems) {
    counts[item.category] = (counts[item.category] || 0) + 1;
  }

  container.innerHTML = categories.map(cat => {
    const isSelected = state.selectedCategory === cat;
    const count = counts[cat] || 0;
    return `
      <button onclick="selectCategory('${cat}')" 
              class="flex-shrink-0 px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                isSelected 
                  ? 'bg-slate-900 text-white shadow-sm' 
                  : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200/80'
              }">
        <span>${cat}</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded-full ${isSelected ? 'bg-slate-700 text-slate-200' : 'bg-slate-100 text-slate-500'} font-semibold">${count}</span>
      </button>
    `;
  }).join('');
}

function renderBillsAndSplits() {
  // Stat cards
  const totalSpentEl = document.getElementById('stat-total-spent');
  const myBalanceEl = document.getElementById('stat-my-balance');
  const myBalanceLabel = document.getElementById('stat-my-balance-label');

  if (totalSpentEl) totalSpentEl.textContent = `$${Number(state.stats.total_spent || 0).toFixed(2)}`;

  const myBalObj = state.balances.find(b => b.id === state.currentMemberId);
  const myBal = myBalObj ? myBalObj.balance : 0.0;

  if (myBalanceEl) {
    if (myBal > 0.01) {
      myBalanceEl.textContent = `+$${myBal.toFixed(2)}`;
      myBalanceEl.className = 'text-2xl font-extrabold text-emerald-600';
      if (myBalanceLabel) myBalanceLabel.textContent = 'You are owed';
    } else if (myBal < -0.01) {
      myBalanceEl.textContent = `-$${Math.abs(myBal).toFixed(2)}`;
      myBalanceEl.className = 'text-2xl font-extrabold text-rose-600';
      if (myBalanceLabel) myBalanceLabel.textContent = 'You owe the group';
    } else {
      myBalanceEl.textContent = '$0.00';
      myBalanceEl.className = 'text-2xl font-extrabold text-slate-800';
      if (myBalanceLabel) myBalanceLabel.textContent = 'All settled up';
    }
  }

  // Debt transfers cards (Who owes whom)
  const transfersContainer = document.getElementById('transfers-container');
  if (transfersContainer) {
    if (state.transfers.length === 0) {
      transfersContainer.innerHTML = `
        <div class="p-6 text-center bg-emerald-50/60 rounded-2xl border border-emerald-100">
          <div class="text-3xl mb-1">🎉</div>
          <div class="text-sm font-bold text-emerald-800">Everyone is fully squared away!</div>
          <div class="text-xs text-emerald-600 mt-0.5">No outstanding grocery debts between friends.</div>
        </div>
      `;
    } else {
      transfersContainer.innerHTML = state.transfers.map(t => {
        const isMeFrom = t.from_id === state.currentMemberId;
        const isMeTo = t.to_id === state.currentMemberId;
        return `
          <div class="p-4 rounded-2xl bg-white border ${isMeFrom ? 'border-rose-200 bg-rose-50/30' : isMeTo ? 'border-emerald-200 bg-emerald-50/30' : 'border-slate-100'} shadow-sm flex items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-2xl flex items-center justify-center font-bold text-sm bg-slate-100 text-slate-700">
                💸
              </div>
              <div>
                <div class="text-xs text-slate-500 font-medium">
                  <strong class="text-slate-800 font-bold">${escapeHtml(t.from_name)}</strong> owes <strong class="text-slate-800 font-bold">${escapeHtml(t.to_name)}</strong>
                </div>
                <div class="text-lg font-black text-slate-900 mt-0.5">$${Number(t.amount).toFixed(2)}</div>
              </div>
            </div>
            <button onclick="openSettleModal(${t.from_id}, '${escapeHtml(t.from_name)}', ${t.to_id}, '${escapeHtml(t.to_name)}', ${t.amount})" 
                    class="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-emerald-600 text-white font-bold text-xs shadow-sm transition flex items-center gap-1.5">
              <span>Settle Up</span>
              <span>✓</span>
            </button>
          </div>
        `;
      }).join('');
    }
  }

  // Bills list
  const billsContainer = document.getElementById('bills-list-container');
  if (billsContainer) {
    if (state.bills.length === 0) {
      billsContainer.innerHTML = `
        <div class="text-center py-8 text-xs text-slate-400">
          No bills recorded yet. Click "Add Supermarket Bill" when someone pays at the checkout counter!
        </div>
      `;
    } else {
      billsContainer.innerHTML = state.bills.map(b => `
        <div class="p-4 rounded-2xl bg-white border border-slate-100 shadow-sm hover:shadow-md transition">
          <div class="flex items-center justify-between gap-2">
            <div>
              <div class="font-bold text-slate-800 text-sm flex items-center gap-2">
                <span>🛒 ${escapeHtml(b.store_name)}</span>
                <span class="text-xs text-slate-400 font-normal">• ${escapeHtml(b.bill_date)}</span>
              </div>
              <div class="text-xs text-slate-500 mt-0.5">
                Paid by <strong class="text-slate-700">${escapeHtml(b.paid_by_name)}</strong>
              </div>
            </div>
            <div class="text-right">
              <div class="text-base font-black text-slate-900">$${Number(b.total_amount).toFixed(2)}</div>
              <div class="text-[10px] text-slate-400">Split by ${b.splits.length} friends</div>
            </div>
          </div>
          <div class="mt-3 pt-2.5 border-t border-slate-50 flex items-center gap-1.5 flex-wrap">
            <span class="text-[10px] text-slate-400 font-semibold mr-1">Split ($${(b.total_amount / (b.splits.length || 1)).toFixed(2)} each):</span>
            ${b.splits.map(s => `
              <span class="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md font-medium">
                ${escapeHtml(s.member_name)}
              </span>
            `).join('')}
          </div>
        </div>
      `).join('');
    }
  }

  // Group balances breakdown table
  const balancesContainer = document.getElementById('member-balances-container');
  if (balancesContainer) {
    balancesContainer.innerHTML = state.balances.map(m => {
      const isPositive = m.balance > 0.01;
      const isNegative = m.balance < -0.01;
      return `
        <div class="flex items-center justify-between py-2 border-b border-slate-50 last:border-0 text-xs">
          <div class="flex items-center gap-2">
            <span class="w-6 h-6 rounded-full text-[10px] flex items-center justify-center text-white font-bold" style="background-color: ${m.avatar_color}">
              ${m.name[0].toUpperCase()}
            </span>
            <span class="font-bold text-slate-700">${escapeHtml(m.name)} ${m.id === state.currentMemberId ? '<span class="text-[10px] text-emerald-600 font-semibold">(You)</span>' : ''}</span>
          </div>
          <div class="font-extrabold ${isPositive ? 'text-emerald-600' : isNegative ? 'text-rose-600' : 'text-slate-400'}">
            ${isPositive ? '+' : ''}$${m.balance.toFixed(2)}
          </div>
        </div>
      `;
    }).join('');
  }
}

function renderActivityFeed() {
  const container = document.getElementById('activity-list-container');
  if (!container) return;

  if (state.activities.length === 0) {
    container.innerHTML = `<div class="text-center py-8 text-xs text-slate-400">No activity yet.</div>`;
    return;
  }

  container.innerHTML = state.activities.map(a => `
    <div class="flex items-start gap-3 p-3 rounded-2xl bg-white border border-slate-100 shadow-sm text-xs">
      <div class="w-7 h-7 rounded-xl flex items-center justify-center font-bold text-xs bg-slate-100 flex-shrink-0 mt-0.5">
        ${a.action_type === 'item_added' ? '➕' : a.action_type === 'item_toggled' ? '🛒' : a.action_type === 'bill_added' ? '🧾' : a.action_type === 'settlement_recorded' ? '💰' : '📢'}
      </div>
      <div class="min-w-0 flex-1">
        <div class="text-slate-800 font-medium leading-relaxed">${escapeHtml(a.message)}</div>
        <div class="text-[10px] text-slate-400 mt-1">${formatTimeAgo(a.created_at)}</div>
      </div>
    </div>
  `).join('');
}

// User Actions
async function addItem(e) {
  e.preventDefault();
  const titleInput = document.getElementById('item-title-input');
  const qtyInput = document.getElementById('item-qty-input');
  const catInput = document.getElementById('item-cat-input');
  const urgentInput = document.getElementById('item-urgent-input');

  const title = titleInput.value.trim();
  const quantity = qtyInput.value.trim() || '1';
  const category = catInput.value;
  const is_urgent = urgentInput ? urgentInput.checked : false;

  if (!title) return;

  try {
    const res = await fetch('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        quantity,
        category,
        is_urgent,
        added_by: state.currentMemberId
      })
    });

    if (res.ok) {
      titleInput.value = '';
      if (urgentInput) urgentInput.checked = false;
      titleInput.focus();
      playSound('add');
      loadState();
    }
  } catch (err) {
    console.error("Failed to add item:", err);
  }
}

async function toggleItemBought(itemId) {
  try {
    const res = await fetch('/api/items/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: itemId,
        member_id: state.currentMemberId
      })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.is_bought) {
        playSound('buy');
      }
      loadState();
    }
  } catch (err) {
    console.error("Failed to toggle item:", err);
  }
}

async function deleteItem(itemId) {
  try {
    const res = await fetch('/api/items/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: itemId,
        member_id: state.currentMemberId
      })
    });
    if (res.ok) {
      loadState();
    }
  } catch (err) {
    console.error("Failed to delete item:", err);
  }
}

async function clearBoughtItems() {
  if (!confirm("Are you sure you want to clear all purchased items from the history?")) return;
  try {
    const res = await fetch('/api/items/clear-bought', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: state.currentMemberId })
    });
    if (res.ok) {
      playSound('clear');
      loadState();
    }
  } catch (err) {
    console.error("Failed to clear bought items:", err);
  }
}

async function submitBill(e) {
  e.preventDefault();
  const storeInput = document.getElementById('bill-store-input');
  const amountInput = document.getElementById('bill-amount-input');
  const payerInput = document.getElementById('bill-payer-select');
  const dateInput = document.getElementById('bill-date-input');

  // Gather selected split members
  const splitCheckboxes = document.querySelectorAll('.split-member-checkbox:checked');
  const splitWith = Array.from(splitCheckboxes).map(cb => parseInt(cb.value));

  const store = storeInput.value.trim() || 'Supermarket';
  const amount = parseFloat(amountInput.value);
  const paidBy = parseInt(payerInput.value);
  const date = dateInput.value;

  if (isNaN(amount) || amount <= 0) {
    showToast("Please enter a valid bill total.", "warning");
    return;
  }
  if (splitWith.length === 0) {
    showToast("Please select at least one friend to split with.", "warning");
    return;
  }

  try {
    const res = await fetch('/api/bills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        store_name: store,
        total_amount: amount,
        paid_by: paidBy,
        split_with: splitWith,
        bill_date: date
      })
    });

    if (res.ok) {
      playSound('bill');
      closeModal('add-bill-modal');
      amountInput.value = '';
      storeInput.value = '';
      showToast(`Bill of $${amount.toFixed(2)} added & split!`, 'purple');
      loadState();
    }
  } catch (err) {
    console.error("Failed to submit bill:", err);
  }
}

async function submitSettlement(e) {
  e.preventDefault();
  const fromId = parseInt(document.getElementById('settle-from-id').value);
  const toId = parseInt(document.getElementById('settle-to-id').value);
  const amount = parseFloat(document.getElementById('settle-amount-input').value);

  if (isNaN(amount) || amount <= 0) return;

  try {
    const res = await fetch('/api/settlements', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from_id: fromId,
        to_id: toId,
        amount: amount
      })
    });
    if (res.ok) {
      playSound('settle');
      closeModal('settle-modal');
      showToast("Settlement recorded! Balances updated.", "success");
      loadState();
    }
  } catch (err) {
    console.error("Failed to settle debt:", err);
  }
}

async function addNewMember(e) {
  e.preventDefault();
  const nameInput = document.getElementById('new-member-name-input');
  const name = nameInput.value.trim();
  if (!name) return;

  const colors = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
  const avatarColor = colors[Math.floor(Math.random() * colors.length)];

  try {
    const res = await fetch('/api/members', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, avatar_color: avatarColor })
    });
    const data = await res.json();
    if (res.ok) {
      nameInput.value = '';
      state.currentMemberId = data.id;
      localStorage.setItem('cartshare_member_id', data.id);
      closeModal('member-modal');
      showToast(`Welcome, ${name}! You are now shopping as ${name}.`, 'success');
      loadState();
    } else {
      showToast(data.error || "Failed to add friend", "warning");
    }
  } catch (err) {
    console.error("Error adding member:", err);
  }
}

// Navigation & Category Filtering
function switchTab(tabId) {
  state.activeTab = tabId;
  const tabs = ['grocery', 'bills', 'activity'];
  tabs.forEach(t => {
    const content = document.getElementById(`tab-content-${t}`);
    const btn = document.getElementById(`tab-btn-${t}`);
    if (content) content.style.display = (t === tabId) ? 'block' : 'none';
    if (btn) {
      if (t === tabId) {
        btn.className = 'flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-slate-900 text-white font-bold text-xs shadow-md transition';
      } else {
        btn.className = 'flex items-center gap-2 px-4 py-2.5 rounded-2xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-bold text-xs transition';
      }
    }
  });
}

function selectCategory(cat) {
  state.selectedCategory = cat;
  renderGroceryList();
}

function onSearchInput(val) {
  state.searchQuery = val;
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
      <option value="${m.id}" ${m.id === state.currentMemberId ? 'selected' : ''}>
        ${escapeHtml(m.name)} ${m.id === state.currentMemberId ? '(You)' : ''}
      </option>
    `).join('');
  }

  if (splitCheckboxesContainer) {
    splitCheckboxesContainer.innerHTML = state.members.map(m => `
      <label class="flex items-center justify-between p-2 rounded-xl border border-slate-200 hover:bg-slate-50 cursor-pointer">
        <span class="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <span class="w-4 h-4 rounded-full" style="background-color: ${m.avatar_color}"></span>
          ${escapeHtml(m.name)}
        </span>
        <input type="checkbox" class="split-member-checkbox custom-checkbox" value="${m.id}" checked />
      </label>
    `).join('');
  }

  openModal('add-bill-modal');
}

function openSettleModal(fromId, fromName, toId, toName, amount) {
  const infoEl = document.getElementById('settle-modal-info');
  const amountInput = document.getElementById('settle-amount-input');
  document.getElementById('settle-from-id').value = fromId;
  document.getElementById('settle-to-id').value = toId;

  if (infoEl) {
    infoEl.innerHTML = `Recording settlement payment from <strong class="text-slate-800">${escapeHtml(fromName)}</strong> to <strong class="text-slate-800">${escapeHtml(toName)}</strong>`;
  }
  if (amountInput) {
    amountInput.value = amount.toFixed(2);
  }

  openModal('settle-modal');
}

function openMemberModal() {
  const listEl = document.getElementById('members-list-selection');
  if (listEl) {
    listEl.innerHTML = state.members.map(m => `
      <div class="flex items-center justify-between p-3 rounded-2xl border ${m.id === state.currentMemberId ? 'border-emerald-500 bg-emerald-50/40' : 'border-slate-100 hover:bg-slate-50'} cursor-pointer transition"
           onclick="selectCurrentMember(${m.id})">
        <div class="flex items-center gap-3">
          <span class="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-xs shadow-sm" style="background-color: ${m.avatar_color}">
            ${m.name[0].toUpperCase()}
          </span>
          <span class="text-sm font-bold text-slate-800">${escapeHtml(m.name)}</span>
        </div>
        ${m.id === state.currentMemberId ? '<span class="text-emerald-600 text-xs font-extrabold">Active ✓</span>' : '<span class="text-xs text-slate-400">Select</span>'}
      </div>
    `).join('');
  }
  openModal('member-modal');
}

function selectCurrentMember(memberId) {
  state.currentMemberId = memberId;
  localStorage.setItem('cartshare_member_id', memberId);
  closeModal('member-modal');
  renderHeader();
  renderBillsAndSplits();
  const m = state.members.find(x => x.id === memberId);
  showToast(`Switched active profile to ${m ? m.name : 'User'}`, 'info');
}

function toggleAudio() {
  state.soundEnabled = !state.soundEnabled;
  renderHeader();
  showToast(state.soundEnabled ? "Audio chimes enabled" : "Audio muted", "info");
}

// Helpers
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr.replace(' ', 'T') + 'Z');
  const now = new Date();
  const diffSec = Math.floor((now - date) / 1000);

  if (diffSec < 45) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

// PWA Installation & Service Worker
let deferredPrompt = null;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(err => {
      console.log('ServiceWorker note:', err);
    });
  });
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const installBtn = document.getElementById('pwa-install-btn');
  if (installBtn) {
    installBtn.classList.remove('hidden');
    installBtn.classList.add('inline-flex');
  }
});

function triggerPwaInstall() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then((choiceResult) => {
      if (choiceResult.outcome === 'accepted') {
        showToast('CartShare app installed to your home screen!', 'success');
      }
      deferredPrompt = null;
      const installBtn = document.getElementById('pwa-install-btn');
      if (installBtn) installBtn.classList.add('hidden');
    });
  } else {
    showToast('On iPhone: Tap Share ➔ "Add to Home Screen" 📲', 'info');
  }
}

// Initialization on DOM Load
window.addEventListener('DOMContentLoaded', () => {
  loadState();
  connectSSE();
  initBrowserNotifications();

  // Close modals on clicking background backdrop
  window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-backdrop')) {
      e.target.classList.add('hidden');
      e.target.classList.remove('flex');
    }
  });
});
