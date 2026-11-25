const THEME_KEY = 'quantterminal_theme'

export function getInitialTheme() {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'dark' || saved === 'light') {
    return saved
  }
  // No saved choice: the terminal defaults to the dark navy workspace.
  return 'dark'
}

export function applyTheme(theme) {
  const activeTheme = theme === 'dark' ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', activeTheme)
  localStorage.setItem(THEME_KEY, activeTheme)
  return activeTheme
}

export function toggleThemeCurrent() {
  const current = document.documentElement.getAttribute('data-theme') || getInitialTheme()
  const next = current === 'dark' ? 'light' : 'dark'
  return applyTheme(next)
}
