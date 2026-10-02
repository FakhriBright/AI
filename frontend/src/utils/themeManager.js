const THEME_KEY = 'quantterminal_theme'

export function getInitialTheme() {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'dark' || saved === 'light') {
    return saved
  }
  // Default to light as per root design system or system preference
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
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
