/** 交互调试：将 last_result 转为步骤编辑器可用的 execution hints */

export function buildDebugExecutionHints(lastResult) {

  if (!lastResult) return null



  const resultType = lastResult.type



  if (resultType === 'verify' && lastResult.step_index != null) {

    const failed = !['success'].includes(String(lastResult.status || '').toLowerCase())

    const stepFailures = failed

      ? [{

          step_index: Number(lastResult.step_index),

          status: lastResult.status === 'ambiguous' ? 'fail' : (lastResult.status || 'fail'),

          message: lastResult.message || '',

          keyword: lastResult.keyword || '',

        }]

      : []

    return {

      has_failure: failed,

      step_failures: stepFailures,

      step_results: failed ? stepFailures : [{

        step_index: Number(lastResult.step_index),

        status: 'success',

        message: lastResult.message || '',

        keyword: lastResult.keyword || '',

      }],

      from_index: lastResult.step_index,

      through_index: lastResult.step_index,

    }

  }



  if (resultType && resultType !== 'run') return null

  if (!lastResult?.steps?.length) return null



  const stepFailures = lastResult.steps

    .filter((item) => ['fail', 'failed', 'error'].includes(String(item?.status || '').toLowerCase()))

    .map((item) => ({

      step_index: Number(item.step_index),

      status: item.status,

      message: item.message || '',

      screenshot: item.screenshot || '',

      keyword: item.keyword || item.desc || '',

    }))



  const stepResults = lastResult.steps.map((item) => ({

    step_index: Number(item.step_index),

    status: item.status,

    message: item.message || '',

    screenshot: item.screenshot || '',

    keyword: item.keyword || item.desc || '',

  }))



  return {

    has_failure: String(lastResult.status || '').toLowerCase() === 'fail',

    step_failures: stepFailures,

    step_results: stepResults,

    from_index: lastResult.from_index,

    through_index: lastResult.through_index,

  }

}



export function buildDebugRunningHints(session) {

  if (!session || session.status !== 'running') return null

  const cmd = session.pending_command

  if (!cmd || cmd.action !== 'run') return null

  const from = Number(cmd.from_index ?? 0)

  const through = Number(cmd.through_index ?? from)

  const stepResults = []

  for (let i = from; i <= through; i += 1) {

    stepResults.push({ step_index: i, status: 'running', message: '执行中…' })

  }

  return {

    has_failure: false,

    step_failures: [],

    step_results: stepResults,

    from_index: from,

    through_index: through,

  }

}



export function mergeDebugExecutionHints(runningHints, resultHints) {

  if (!runningHints && !resultHints) return null

  if (!runningHints) return resultHints

  if (!resultHints) return runningHints

  const finishedMap = new Map(

    (resultHints.step_results || []).map((item) => [Number(item.step_index), item]),

  )

  const mergedResults = (runningHints.step_results || []).map((item) => {

    const finished = finishedMap.get(Number(item.step_index))

    if (finished && String(finished.status).toLowerCase() !== 'running') {

      return finished

    }

    return item

  })

  return {

    ...resultHints,

    step_results: mergedResults.length ? mergedResults : resultHints.step_results,

    step_failures: resultHints.step_failures || [],

    has_failure: resultHints.has_failure,

  }

}



export function buildInteractiveDebugHints(session) {

  return mergeDebugExecutionHints(

    buildDebugRunningHints(session),

    buildDebugExecutionHints(session?.last_result),

  )

}



export function getDebugStepResult(debugHints, stepIndex) {
  if (!debugHints?.step_results?.length) return null
  const idx = Number(stepIndex)
  const matches = debugHints.step_results.filter((item) => Number(item.step_index) === idx)
  if (!matches.length) return null
  const failed = matches.find((item) => ['fail', 'failed', 'error'].includes(String(item?.status || '').toLowerCase()))
  if (failed) return failed
  const running = matches.find((item) => String(item?.status || '').toLowerCase() === 'running')
  if (running) return running
  return matches[matches.length - 1]
}



export function formatDebugStepStatus(status) {

  const key = String(status || '').toLowerCase()

  if (key === 'success') return '成功'

  if (key === 'fail' || key === 'failed') return '失败'

  if (key === 'running') return '执行中'

  if (key === 'error') return '错误'

  return status || '—'

}

export function formatIdleRemaining(seconds) {
  const total = Math.max(0, Number(seconds) || 0)
  if (total <= 0) return '即将'
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    return `${hours} 小时 ${mins} 分`
  }
  if (minutes > 0) return `${minutes} 分 ${secs} 秒`
  return `${secs} 秒`
}

/** 将步骤下标合并为连续区间 [[from, through], ...] */
export function groupContiguousStepIndices(indices) {
  if (!indices?.length) return []
  const sorted = [...new Set(indices.map((i) => Number(i)))].filter((i) => !Number.isNaN(i)).sort((a, b) => a - b)
  if (!sorted.length) return []
  const segments = []
  let from = sorted[0]
  let through = sorted[0]
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i] === through + 1) {
      through = sorted[i]
    } else {
      segments.push([from, through])
      from = through = sorted[i]
    }
  }
  segments.push([from, through])
  return segments
}

/** 格式化多步调试范围文案，如「第 2～4 步、第 7 步」 */
export function formatDebugStepRange(indices) {
  const segments = groupContiguousStepIndices(indices)
  if (!segments.length) return ''
  return segments
    .map(([from, through]) => (from === through ? `第 ${from + 1} 步` : `第 ${from + 1}～${through + 1} 步`))
    .join('、')
}

/** 由 resolve-run-segments 的 editor_map 构建 session -> editor 反查表 */
export function buildSessionToEditorMap(editorMapPayload) {
  const reverse = {}
  for (const row of editorMapPayload || []) {
    const editorIdx = Number(row.editor_index)
    const from = Number(row.from_index)
    const through = Number(row.through_index)
    if (Number.isNaN(editorIdx) || Number.isNaN(from) || Number.isNaN(through)) continue
    for (let s = from; s <= through; s += 1) {
      reverse[s] = editorIdx
    }
  }
  return reverse
}

/** 将会话侧 step_index 映射为编辑器步骤下标 */
export function mapSessionStepResultsToEditor(stepResults, sessionToEditorMap) {
  return (stepResults || []).map((item) => {
    const sessionIdx = Number(item?.step_index)
    const editorIdx = sessionToEditorMap[sessionIdx] ?? sessionIdx
    return {
      ...item,
      session_step_index: sessionIdx,
      step_index: editorIdx,
    }
  })
}

/** 合并多段调试 last_result（steps 已映射为编辑器下标） */
export function mergeDebugRunStepResults(resultList) {
  const allSteps = []
  let overallStatus = 'success'
  for (const result of resultList || []) {
    if (!result?.steps?.length) continue
    allSteps.push(...result.steps)
    if (String(result.status || '').toLowerCase() === 'fail') {
      overallStatus = 'fail'
    }
  }
  if (!allSteps.length) return null
  const editorIndices = allSteps.map((s) => Number(s.step_index)).filter((i) => !Number.isNaN(i))
  return {
    type: 'run',
    status: overallStatus,
    from_index: editorIndices.length ? Math.min(...editorIndices) : 0,
    through_index: editorIndices.length ? Math.max(...editorIndices) : 0,
    steps: allSteps,
  }
}

