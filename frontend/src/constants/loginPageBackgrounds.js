import loginBgLegacy from '@/assets/images/login_bg.jpg'
import loginBgOpt1 from '@/assets/images/login_bg_pro_opt1.png'
import loginBgOpt2 from '@/assets/images/login_bg_pro_opt2.png'
import loginBgOpt3 from '@/assets/images/login_bg_pro_opt3.png'
import loginBgOpt4 from '@/assets/images/login_bg_pro_opt4.png'
import loginBgClassic1 from '@/assets/images/login_bg_classic1.png'
import loginBgClassic2 from '@/assets/images/login_bg_classic2.png'
import loginBgClassic3 from '@/assets/images/login_bg_classic3.png'
import loginBgClassic4 from '@/assets/images/login_bg_classic4.png'

/** 清新 Pro 简约内置背景（推荐，无 UI 干扰元素） */
export const PRO_BG_OPTIONS = [
  { key: 'opt1', label: '方案 1', desc: '玻璃质感积木 + 淡蓝雾面', asset: loginBgOpt1 },
  { key: 'opt2', label: '方案 2', desc: '浅蓝渐变 + 低对比网格', asset: loginBgOpt2 },
  { key: 'opt3', label: '方案 3（默认）', desc: '紫蓝极光 + 散落方块', asset: loginBgOpt3 },
  { key: 'opt4', label: '方案 4', desc: '极简光感 + 底部等距块', asset: loginBgOpt4 },
]

/** 经典风格内置背景 */
export const CLASSIC_BG_OPTIONS = [
  { key: 'classic1', label: '商务深蓝', desc: '稳重企业深蓝金线（默认）', asset: loginBgClassic1 },
  { key: 'classic2', label: '科技电路', desc: '炭灰蓝电路纹理', asset: loginBgClassic2 },
  { key: 'classic3', label: '青灰光束', desc: '青灰专业光束', asset: loginBgClassic3 },
  { key: 'classic4', label: '窗景深蓝', desc: '深蓝窗景 bokeh', asset: loginBgClassic4 },
  { key: 'legacy', label: '经典摄影（旧版）', desc: '原乐高积木摄影背景', asset: loginBgLegacy },
]

export const LOGIN_BG_ASSETS = {
  opt1: loginBgOpt1,
  opt2: loginBgOpt2,
  opt3: loginBgOpt3,
  opt4: loginBgOpt4,
  classic1: loginBgClassic1,
  classic2: loginBgClassic2,
  classic3: loginBgClassic3,
  classic4: loginBgClassic4,
  legacy: loginBgLegacy,
  // 旧 key 兼容
  pro1: loginBgOpt1,
  pro2: loginBgOpt2,
  pro3: loginBgOpt3,
  pro4: loginBgOpt4,
  classic: loginBgLegacy,
}

export const LOGIN_PAGE_DEFAULTS = {
  pro_bg_key: 'opt3',
  classic_bg_key: 'classic1',
  pro_bg_url: '',
  classic_bg_url: '',
  welcome_title: '欢迎登录 BrickCore',
  footer_text: '© 2025-2026 BrickCore v1.2.0. All Rights Reserved.',
  show_register: true,
  bg_brick_count: 30,
  bg_star_count: 15,
  bg_dot_count: 15,
  bg_motion_enabled: true,
}

export const LOGIN_MOTION_LIMITS = {
  brick: { min: 0, max: 60 },
  star: { min: 0, max: 40 },
  dot: { min: 0, max: 40 },
}

export function resolveStaticUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  const baseAPI = import.meta.env.VITE_BASE_API || ''
  try {
    const origin = new URL(baseAPI, window.location.href).origin
    return `${origin}${url.startsWith('/') ? url : `/${url}`}`
  } catch {
    return url.startsWith('/') ? url : `/${url}`
  }
}

export function resolveLoginBgAsset(config, uiTheme) {
  const isPro = uiTheme === 'pro'
  const key = isPro ? config?.pro_bg_key : config?.classic_bg_key
  const customUrl = isPro ? config?.pro_bg_url : config?.classic_bg_url
  if (key === 'custom' && customUrl) {
    return resolveStaticUrl(customUrl)
  }
  const fallback = isPro ? LOGIN_PAGE_DEFAULTS.pro_bg_key : LOGIN_PAGE_DEFAULTS.classic_bg_key
  return LOGIN_BG_ASSETS[key] || LOGIN_BG_ASSETS[fallback] || loginBgOpt3
}

export function buildLoginBackgroundStyle(config, uiTheme) {
  const url = resolveLoginBgAsset(config, uiTheme)
  if (uiTheme === 'pro') {
    return {
      background: `linear-gradient(135deg, rgba(238, 243, 255, .32) 0%, rgba(248, 250, 255, .28) 100%), url(${url}) center/cover no-repeat`,
    }
  }
  return {
    background: `linear-gradient(rgba(0,0,0,.08), rgba(0,0,0,.08)), url(${url}) center/cover no-repeat`,
  }
}

export function pickBgKeyForTheme(config, uiTheme) {
  if (!config) {
    return uiTheme === 'pro' ? LOGIN_PAGE_DEFAULTS.pro_bg_key : LOGIN_PAGE_DEFAULTS.classic_bg_key
  }
  return uiTheme === 'pro' ? config.pro_bg_key : config.classic_bg_key
}
