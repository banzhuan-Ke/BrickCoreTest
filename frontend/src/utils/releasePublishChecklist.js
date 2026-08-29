/**
 * 发布前检查清单（Phase 4）— 由质量预览推导四项红绿灯
 */

/**
 * @param {object|null} qualityPreview
 * @returns {{ items: Array, allPass: boolean, readyHint: string }}
 */
export function computePublishChecklist(qualityPreview) {
  const m = qualityPreview?.metrics || {}
  const snap = qualityPreview?.latest_snapshot
  const hasValidWaiver = !!qualityPreview?.has_valid_waiver
  const snapshotStale = !!qualityPreview?.snapshot_stale

  const requiredTotal = m.required_total || 0
  const requiredDone = m.required_done || 0
  const requiredOk = requiredTotal > 0 && requiredDone >= requiredTotal

  const blocker = m.blocker_open || 0
  const critical = m.critical_open || 0
  const defectsOk = blocker === 0 && critical === 0

  const highRiskGap = m.high_risk_without_result || 0
  const highRiskOk = highRiskGap === 0

  let snapshotStatus = 'pending'
  let snapshotDetail = '尚未生成质量快照'
  if (snap) {
    if (hasValidWaiver || snap.conclusion === 'conditional_pass') {
      snapshotStatus = hasValidWaiver ? 'pass' : 'warn'
      snapshotDetail = hasValidWaiver
        ? '有效豁免（有条件通过）'
        : '有条件通过快照，豁免已失效或未批准'
    } else if (snap.conclusion === 'pass') {
      if (snapshotStale) {
        snapshotStatus = 'fail'
        snapshotDetail = 'pass 快照已陈旧，请重新生成'
      } else {
        snapshotStatus = 'pass'
        snapshotDetail = '合格快照有效'
      }
    } else {
      snapshotStatus = 'fail'
      snapshotDetail = `最近快照：${snap.conclusion || '未通过'}`
    }
  }

  const items = [
    {
      id: 'required',
      title: '必测完成',
      status: !qualityPreview
        ? 'pending'
        : requiredOk
          ? 'pass'
          : requiredTotal <= 0
            ? 'fail'
            : 'fail',
      detail: !qualityPreview
        ? '请先刷新质量预览'
        : requiredTotal <= 0
          ? '尚无必测计划项'
          : `${requiredDone}/${requiredTotal}`,
      action: 'quality'
    },
    {
      id: 'defects',
      title: 'Blocker/Critical',
      status: !qualityPreview ? 'pending' : defectsOk ? 'pass' : 'fail',
      detail: !qualityPreview
        ? '请先刷新质量预览'
        : defectsOk
          ? '无未关闭阻塞/严重缺陷'
          : `Blocker ${blocker} · Critical ${critical}`,
      action: 'defects'
    },
    {
      id: 'high_risk',
      title: '高风险覆盖',
      status: !qualityPreview ? 'pending' : highRiskOk ? 'pass' : 'fail',
      detail: !qualityPreview
        ? '请先刷新质量预览'
        : highRiskOk
          ? '高/严重风险项均有有效结果'
          : `${highRiskGap} 项高风险无有效结果`,
      action: 'scopes'
    },
    {
      id: 'snapshot',
      title: '质量快照',
      status: snapshotStatus,
      detail: snapshotDetail,
      action: 'quality'
    }
  ]

  const allPass = items.every((i) => i.status === 'pass')
  const readyHint = allPass
    ? '检查项均已通过，可尝试变更「就绪」或「发布」'
    : '请先处理红色/黄色项后再收口发布'

  return { items, allPass, readyHint }
}

export function checklistStatusTagType(status) {
  return (
    {
      pass: 'success',
      fail: 'danger',
      warn: 'warning',
      pending: 'info'
    }[status] || 'info'
  )
}

export function checklistStatusLabel(status) {
  return (
    {
      pass: '通过',
      fail: '未通过',
      warn: '需关注',
      pending: '待检查'
    }[status] || status
  )
}
