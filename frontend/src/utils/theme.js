export const UI_THEMES = {
    classic: 'classic',
    pro: 'pro',
}

export const UI_THEME_OPTIONS = [
    { value: UI_THEMES.classic, label: '经典风格', desc: '原有界面风格，支持暗黑模式' },
    { value: UI_THEMES.pro, label: '清新 Pro', desc: '柔和蓝紫渐变，圆角卡片布局' },
]

export function applyUiTheme(theme, darkMode = false) {
    const html = document.documentElement
    const isPro = theme === UI_THEMES.pro

    html.classList.toggle('theme-pro', isPro)

    if (isPro) {
        html.classList.remove('dark')
        html.style.colorScheme = 'light'
        return
    }

    html.classList.toggle('dark', !!darkMode)
    html.style.colorScheme = darkMode ? 'dark' : 'light'
}

export function initUiTheme(theme, darkMode = false) {
    applyUiTheme(theme, darkMode)
}
