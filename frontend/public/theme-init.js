// Apply before app/CSS paint; storage can be unavailable in private environments.
(() => {
  let preference = { theme: 'orange', mode: 'dark' }
  try {
    const saved = JSON.parse(localStorage.getItem('databridge.appearance') || 'null')
    if (saved && ['orange', 'blue', 'emerald'].includes(saved.theme) && ['light', 'dark', 'system'].includes(saved.mode)) preference = saved
  } catch { /* Use defaults. */ }
  const root = document.documentElement
  root.dataset.theme = preference.theme
  root.dataset.appearance = preference.mode
  root.dataset.mode = preference.mode === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : preference.mode
})()
