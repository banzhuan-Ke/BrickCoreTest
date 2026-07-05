/**
 * 将助手回答中的实体 ID 转为 Markdown 内链（hash 路由）
 */

function mdLink(label, hashPath) {
  return `[${label}](${hashPath})`
}

function alreadyLinked(text, index) {
  const before = text.slice(Math.max(0, index - 80), index)
  return before.includes('[') && !before.slice(before.lastIndexOf('[')).includes(']')
}

function isMarkdownHeader(line) {
  return /^#{1,6}\s/.test(line.trim())
}

function sectionFromHeader(line) {
  const h = line.trim().replace(/^#{1,6}\s*/, '')
  if (/app\s*用例|app用例/i.test(h)) return 'app_case'
  if (/app\s*套件|app套件/i.test(h)) return 'app_suite'
  if (/app\s*计划|app测试计划/i.test(h)) return 'app_plan'
  if (/接口.*用例|api.*用例/i.test(h)) return 'api_case'
  if (/ui\s*用例|web\s*用例|界面用例/i.test(h)) return 'ui_case'
  if (/ui\s*计划|web\s*计划|界面计划/i.test(h)) return 'ui_plan'
  if (/接口套件|api\s*套件/i.test(h)) return 'api_suite'
  if (/接口计划|api\s*计划|接口测试计划/i.test(h)) return 'api_plan'
  if (/压测|性能/i.test(h)) return 'perf'
  if (/需求/i.test(h)) return 'requirement'
  return null
}

function lineSectionHint(line) {
  if (/app\s*用例|app用例/i.test(line)) return 'app_case'
  if (/app\s*套件|app套件/i.test(line)) return 'app_suite'
  if (/app\s*计划|app测试计划/i.test(line)) return 'app_plan'
  if (/接口.*用例/i.test(line)) return 'api_case'
  if (/ui\s*用例|web\s*用例|界面用例/i.test(line)) return 'ui_case'
  if (/ui\s*计划|web\s*计划/i.test(line) && !/app/i.test(line)) return 'ui_plan'
  if (/接口套件|api\s*套件/i.test(line)) return 'api_suite'
  if (/接口计划|api\s*计划/i.test(line)) return 'api_plan'
  if (/压测|性能场景/i.test(line)) return 'perf'
  if (/需求文档|需求\s*[（(]/i.test(line)) return 'requirement'
  return null
}

function routeForSection(section, id) {
  switch (section) {
    case 'app_case':
      return `#/app-case/edit/${id}`
    case 'app_suite':
      return `#/app-suite/edit/${id}`
    case 'app_plan':
      return `#/app-plan/edit/${id}`
    case 'ui_case':
      return `#/case/edit/${id}`
    case 'ui_plan':
      return `#/task/edit/${id}`
    case 'api_case':
      return `#/api-case?case_id=${id}`
    case 'api_suite':
      return `#/api-suite/${id}`
    case 'api_plan':
      return `#/api-plan/${id}`
    case 'requirement':
      return `#/ai-requirements?requirement_id=${id}`
    case 'perf':
      return `#/perf-scene/edit/${id}`
    default:
      return null
  }
}

function applyRulesOnLine(line, rules) {
  let result = line
  for (const rule of rules) {
    result = result.replace(rule.pattern, (...args) => {
      const match = args[0]
      const offset = args[args.length - 2]
      if (typeof offset === 'number' && alreadyLinked(result, offset)) {
        return match
      }
      const id = rule.pickId(args)
      if (!id) return match
      return mdLink(match, rule.route(id))
    })
  }
  return result
}

const EXPLICIT_RULES = [
  {
    pattern: /app_case_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/app-case/edit/${id}`,
  },
  {
    pattern: /app_suite_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/app-suite/edit/${id}`,
  },
  {
    pattern: /app_plan_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/app-plan/edit/${id}`,
  },
  {
    pattern: /ui_case_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/case/edit/${id}`,
  },
  {
    pattern: /suite_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-suite/${id}`,
  },
  {
    pattern: /plan_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-plan/${id}`,
  },
  {
    pattern: /api_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module?api_id=${id}`,
  },
  {
    pattern: /case_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-case?case_id=${id}`,
  },
  {
    pattern: /requirement_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/ai-requirements?requirement_id=${id}`,
  },
  {
    pattern: /task_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/task/edit/${id}`,
  },
  {
    pattern: /perf_scene_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-scene/edit/${id}`,
  },
  {
    pattern: /perf_record_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-report/${id}`,
  },
  {
    pattern: /target_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module/report/${id}`,
  },
  {
    pattern: /template_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-data-factory?template_id=${id}`,
  },
  {
    pattern: /datasource_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-data-factory?datasource_id=${id}`,
  },
  {
    pattern: /set_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/ai-qa-eval?set_id=${id}`,
  },
  {
    pattern: /(?:App\s*用例|App用例)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/app-case/edit/${id}`,
  },
  {
    pattern: /(?:App\s*套件|App套件)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/app-suite/edit/${id}`,
  },
  {
    pattern: /(?:App\s*计划|App测试计划)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/app-plan/edit/${id}`,
  },
  {
    pattern: /(?:接口测试计划|API计划|接口计划)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-plan/${id}`,
  },
  {
    pattern: /(?:压测场景|性能场景)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-scene/edit/${id}`,
  },
  {
    pattern: /(?:压测记录|性能记录)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-report/${id}`,
  },
  {
    pattern: /(?:接口套件|API套件)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-suite/${id}`,
  },
  {
    pattern: /(?:接口定义|API接口|接口)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module?api_id=${id}`,
  },
  {
    pattern: /(?:需求文档|需求)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/ai-requirements?requirement_id=${id}`,
  },
  {
    pattern: /(?:UI计划|UI 计划|Web计划)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/task/edit/${id}`,
  },
  {
    pattern: /(?:UI用例|Web用例|Web UI用例|界面用例)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/case/edit/${id}`,
  },
  {
    pattern: /(?:SQL模板|SQL 模板|数据模板)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-data-factory?template_id=${id}`,
  },
  {
    pattern: /(?:数据源|数据工厂数据源)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-data-factory?datasource_id=${id}`,
  },
  {
    pattern: /(?:评测集|问答评测集)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/ai-qa-eval?set_id=${id}`,
  },
  {
    pattern: /(?:接口执行记录)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module/report/${id}`,
  },
]

function linkContextualIds(line, section) {
  if (!section || line.includes('](#/')) return line
  let result = line
  const route = (id) => routeForSection(section, id)

  result = result.replace(/\bid\s*=\s*(\d+)/gi, (match, id, offset) => {
    if (alreadyLinked(result, offset)) return match
    const path = route(id)
    return path ? mdLink(match, path) : match
  })

  // 列表项「· id=3：」或「- **id=3**」已在上面处理；兼容「#3：」写法（非 Markdown 标题）
  result = result.replace(/(?<![#\w])#(\d+)\b/g, (match, id, offset) => {
    if (alreadyLinked(result, offset)) return match
    const path = route(id)
    return path ? mdLink(match, path) : match
  })

  return result
}

function refineLineFallback(line) {
  if (line.includes('](#/')) return line
  if (/app/i.test(line)) return line

  let result = line
  if (/需求/.test(line)) {
    result = result.replace(/(?<![#\w])#(\d+)\b/g, (m, id, off) =>
      alreadyLinked(result, off) ? m : mdLink(m, `#/ai-requirements?requirement_id=${id}`)
    )
  } else if (/接口/.test(line) && /用例/.test(line)) {
    result = result.replace(/(?<![#\w])#(\d+)\b/g, (m, id, off) =>
      alreadyLinked(result, off) ? m : mdLink(m, `#/api-case?case_id=${id}`)
    )
  } else if (/接口/.test(line)) {
    result = result.replace(/(?<![#\w])#(\d+)\b/g, (m, id, off) =>
      alreadyLinked(result, off) ? m : mdLink(m, `#/api-module?api_id=${id}`)
    )
  } else if (/计划|task/i.test(line)) {
    result = result.replace(/(?<![#\w])#(\d+)\b/g, (m, id, off) =>
      alreadyLinked(result, off) ? m : mdLink(m, `#/task/edit/${id}`)
    )
  } else if (/UI|用例/.test(line)) {
    result = result.replace(/(?<![#\w])#(\d+)\b/g, (m, id, off) =>
      alreadyLinked(result, off) ? m : mdLink(m, `#/case/edit/${id}`)
    )
  }
  return result
}

function linkifyByLines(text) {
  let section = null
  return text
    .split('\n')
    .map((line) => {
      if (isMarkdownHeader(line)) {
        const detected = sectionFromHeader(line)
        if (detected) section = detected
        return line
      }

      const hint = lineSectionHint(line)
      if (hint) section = hint

      let result = applyRulesOnLine(line, EXPLICIT_RULES)
      result = linkContextualIds(result, section)
      result = refineLineFallback(result)
      return result
    })
    .join('\n')
}

export function linkifyAssistantContent(content) {
  if (!content) return ''
  return linkifyByLines(String(content))
}
