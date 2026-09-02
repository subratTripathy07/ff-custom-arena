// ============================================================
// 🔥 FF CUSTOM ARENA — CLIENT-SIDE JAVASCRIPT & SOCKET.IO
// ============================================================

// ---------- 1. Theme toggle (dark/light) ----------
(function () {
  const root = document.documentElement;
  const toggle = document.getElementById('themeToggle');
  const saved = localStorage.getItem('ff-theme') || 'dark';
  root.setAttribute('data-theme', saved);

  function updateIcon() {
    if (!toggle) return;
    const isLight = root.getAttribute('data-theme') === 'light';
    toggle.innerHTML = isLight ? '<i class="fa-solid fa-sun text-warning"></i>' : '<i class="fa-solid fa-moon"></i>';
  }
  updateIcon();

  if (toggle) {
    toggle.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      localStorage.setItem('ff-theme', next);
      updateIcon();
    });
  }
})();

// ---------- 2. Mobile Drawer Navigation Toggle ----------
document.addEventListener('DOMContentLoaded', () => {
  const mobileToggle = document.getElementById('mobileMenuToggle');
  const drawer = document.getElementById('mobileDrawer');

  if (mobileToggle && drawer) {
    mobileToggle.addEventListener('click', () => {
      drawer.classList.toggle('is-open');
    });

    // Close drawer when clicking outside
    document.addEventListener('click', (e) => {
      if (!drawer.contains(e.target) && !mobileToggle.contains(e.target) && drawer.classList.contains('is-open')) {
        drawer.classList.remove('is-open');
      }
    });
  }
});

// ---------- 3. Toast Notifications Generator ----------
function showToast(message, type = 'info', icon = 'fa-circle-info') {
  let stack = document.getElementById('toastStack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toastStack';
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <i class="fa-solid ${icon}"></i>
    <span>${message}</span>
  `;

  stack.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = 'opacity .3s ease, transform .3s ease';
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(30px)';
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

// Auto dismiss pre-rendered toasts
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.toast').forEach((toast, i) => {
    setTimeout(() => {
      toast.style.transition = 'opacity .3s ease, transform .3s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(30px)';
      setTimeout(() => toast.remove(), 300);
    }, 4000 + i * 300);
  });
});

// ---------- 4. One-Click Copy to Clipboard ----------
function copyToClipboard(text, label = 'Text') {
  if (!navigator.clipboard) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showToast(`${label} copied to clipboard!`, 'success', 'fa-copy');
    return;
  }

  navigator.clipboard.writeText(text).then(() => {
    showToast(`${label} copied to clipboard!`, 'success', 'fa-copy');
  }).catch(() => {
    showToast(`Failed to copy ${label}`, 'danger', 'fa-triangle-exclamation');
  });
}

// ---------- 5. Live Countdown Timer Engine ----------
function initCountdowns() {
  const countdownEls = document.querySelectorAll('[data-countdown]');
  if (!countdownEls.length) return;

  function updateAll() {
    const now = new Date().getTime();
    countdownEls.forEach((el) => {
      const targetStr = el.getAttribute('data-countdown');
      const target = new Date(targetStr).getTime();
      const diff = target - now;

      const timerDisplay = el.querySelector('.countdown-timer') || el;

      if (diff <= 0) {
        timerDisplay.textContent = 'EXPIRED / RELEASED';
        timerDisplay.classList.add('text-success');
        return;
      }

      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      let text = '';
      if (days > 0) text += `${days}d `;
      text += `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

      timerDisplay.textContent = text;
    });
  }

  updateAll();
  setInterval(updateAll, 1000);
}

document.addEventListener('DOMContentLoaded', initCountdowns);

// ---------- 6. Live Socket.IO Listeners ----------
(function () {
  if (typeof io === 'undefined') return;

  try {
    const socket = io();

    socket.on('connect', () => {
      // If on a tournament page, subscribe to the tournament room
      const tourEl = document.querySelector('[data-tournament-id]');
      if (tourEl) {
        const tId = parseInt(tourEl.getAttribute('data-tournament-id'), 10);
        if (tId) socket.emit('subscribe_tournament', { tournament_id: tId });
      }
    });

    socket.on('notification', (data) => {
      showToast(data.message || 'New notification', 'info', data.icon || 'fa-bell');
      // Update badge if exists
      const badge = document.querySelector('.notif-badge');
      if (badge) {
        const count = parseInt(badge.textContent, 10) || 0;
        badge.textContent = count + 1;
      }
    });

    socket.on('room_released', (data) => {
      showToast(`🔑 Room credentials have been released!`, 'success', 'fa-key');
      // Refresh match page to show revealed password if on this match
      if (window.location.pathname.includes(`/matches/${data.match_id}`)) {
        setTimeout(() => window.location.reload(), 1500);
      }
    });

    socket.on('match_status', (data) => {
      showToast(`Match status updated to ${data.status.toUpperCase()}`, 'warning', 'fa-signal');
    });

    socket.on('result_verified', (data) => {
      showToast(`🏆 Score verified: ${data.points} points awarded.`, 'success', 'fa-award');
    });

    socket.on('announcement', (data) => {
      showToast(`📢 ${data.title}: ${data.message}`, 'warning', 'fa-bullhorn');
    });

  } catch (err) {
    console.log('SocketIO init notice:', err);
  }
})();
