/** 版本状态变更前的门禁确认文案 */
import { ElMessageBox } from 'element-plus'
import { releaseStatusLabel } from '@/utils/testReleaseStatus'
import { testReleaseApi } from '@/api/testManagement'

const QUALITY_LABELS = {
  pass: '通过',
  conditional_pass: '有条件通过',
  failed: '未通过',
  blocked: '阻塞'
}

function qualityLabel(c) {
  return QUALITY_LABELS[c] || c || '—'
}

/**
 * ready / released 变更前拉预览并确认；其它状态仅简单确认。
 * @returns {Promise<boolean>} 用户是否确认
 */
export async function confirmReleaseStatusChange({
  target,
  releaseId,
  projectId,
  releaseName = '',
  canViewQuality = true
}) {
  const label = releaseStatusLabel(target)
  const safeName = escapeHtml(String(releaseName || '').slice(0, 80))
  const titleHint = safeName ? `「${safeName}」` : ''

  if (target !== 'ready' && target !== 'released') {
    try {
      await ElMessageBox.confirm(
        `确认将版本${releaseName ? `「${String(releaseName).slice(0, 80)}」` : ''}变更为「${label}」？`,
        '变更状态',
        { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
      )
      return true
    } catch {
      return false
    }
  }

  let preview = null
  if (canViewQuality && projectId && releaseId) {
    try {
      const res = await testReleaseApi.qualityPreview(releaseId, projectId)
      preview = res.data?.data || null
    } catch {
      preview = null
    }
  }

  const lines = [
    `<p>确认将版本${titleHint}变更为 <b>${escapeHtml(label)}</b>？</p>`
  ]
  if (preview) {
    const m = preview.metrics || {}
    lines.push(
      `<p>实时门禁：<b>${qualityLabel(preview.conclusion)}</b>` +
        `（必测 ${m.required_done ?? '—'}/${m.required_total ?? '—'}，` +
        `通过率 ${m.pass_rate != null ? Math.round(Number(m.pass_rate) * 100) + '%' : '—'}）</p>`
    )
    if (preview.gate_enforce) {
      lines.push('<p>当前为<strong>强制模式</strong>：未通过且无有效豁免时发布将被拦截。</p>')
    } else if (target === 'released') {
      lines.push('<p>当前为<strong>提示模式</strong>：发布未通过仅警告，仍可能放行。</p>')
    }
    if (target === 'ready') {
      lines.push('<p>进入就绪<strong>始终强制</strong>要求合格快照或有效豁免（豁免 14 天内有效）。</p>')
    }
    if (preview.snapshot_stale) {
      lines.push('<p style="color:#c45656">最近 pass 快照已过期（质量已回退），请先重新生成快照或批准豁免。</p>')
    }
    if (preview.has_valid_waiver) {
      const reason = preview.latest_snapshot?.waiver_reason || ''
      lines.push(`<p>存在有效豁免${reason ? `：${escapeHtml(String(reason).slice(0, 80))}` : ''}。</p>`)
    } else if (preview.latest_snapshot?.conclusion === 'conditional_pass') {
      lines.push('<p style="color:#b88230">豁免已失效或过期，需重新批准。</p>')
    }
  } else {
    lines.push('<p>未能加载质量预览，仍可继续；服务端会再次校验门禁。</p>')
  }

  try {
    await ElMessageBox.confirm(lines.join(''), '质量门禁确认', {
      type: 'warning',
      dangerouslyUseHTMLString: true,
      confirmButtonText: '确认变更',
      cancelButtonText: '取消',
      customClass: 'tm-quality-confirm'
    })
    return true
  } catch {
    return false
  }
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
