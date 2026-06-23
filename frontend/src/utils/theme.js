import { useDark } from '@vueuse/core'

export const UI_THEMES = {
    classic: 'classic',
    pro: 'pro',
    compact: 'compact',
}

export const UI_THEME_OPTIONS = [
    { value: UI_THEMES.classic, label: '经典风格', desc: '原有界面风格，支持暗黑模式' },
    { value: UI_THEMES.pro, label: '清新 Pro', desc: '柔和蓝紫渐变，圆角卡片布局' },
    { value: UI_THEMES.compact, label: '紧凑经典', desc: '侧栏与表格更紧凑，适合大屏专业场景' },
]

let darkModeRef = null

/** 与 @vueuse/core useDark 同步，避免切 Pro 后 html.dark 残留 */
function syncDocumentDark(theme, darkMode) {
    if (!darkModeRef) {
        darkModeRef = useDark()
    }
    const isPro = theme === UI_THEMES.pro
    const shouldDark = !isPro && !!darkMode
    darkModeRef.value = shouldDark
    document.documentElement.classList.toggle('dark', shouldDark)
    document.documentElement.style.colorScheme = shouldDark ? 'dark' : 'light'
}

export function isValidUiTheme(theme) {
    return Object.values(UI_THEMES).includes(theme)
}

export function applyUiTheme(theme, darkMode = false) {
    const html = document.documentElement
    const isPro = theme === UI_THEMES.pro
    const isCompact = theme === UI_THEMES.compact

    html.classList.toggle('theme-pro', isPro)
    html.classList.toggle('theme-compact', isCompact)

    syncDocumentDark(theme, darkMode)
}

export function initUiTheme(theme, darkMode = false) {
    applyUiTheme(theme, darkMode)
}
