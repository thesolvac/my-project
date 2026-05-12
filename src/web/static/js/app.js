/**
 * APME – Global JavaScript
 * Provides shared utilities used across all pages.
 */

'use strict';

// ── Bootstrap tooltip initialisation ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltips.forEach(el => new bootstrap.Tooltip(el));

  // Auto-dismiss alerts after 5 seconds
  document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });
});

// ── Utility: format bytes ──────────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(2) + ' MB';
  if (bytes >= 1_024)     return (bytes / 1_024).toFixed(1)     + ' KB';
  return bytes + ' B';
}

// ── Utility: escape HTML ───────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
