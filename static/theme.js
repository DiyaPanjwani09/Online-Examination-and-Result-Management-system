/**
 * theme.js — Dark / Light Mode Toggle
 * Persists user preference in localStorage.
 * Apply data-theme="light" on <html> for light mode.
 */

(function () {
  const STORAGE_KEY = 'examportal-theme';

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    updateToggleButton(theme);
  }

  function updateToggleButton(theme) {
    const btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    if (theme === 'light') {
      btn.innerHTML = '☀️';
      btn.title = 'Switch to Dark Mode';
    } else {
      btn.innerHTML = '🌙';
      btn.title = 'Switch to Light Mode';
    }
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Expose globally so onclick="toggleTheme()" works
  window.toggleTheme = toggleTheme;

  // Apply saved or default theme immediately (before page paint)
  const saved = localStorage.getItem(STORAGE_KEY) || 'dark';
  applyTheme(saved);

  // Re-run after DOM is ready so button icon is also updated
  document.addEventListener('DOMContentLoaded', function () {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    updateToggleButton(current);
  });
})();
