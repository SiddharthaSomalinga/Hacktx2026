// Applies a saved theme override before first paint, so the page never flashes the wrong palette.
try {
  var theme = localStorage.getItem('gs-theme')
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme
} catch (e) {}
