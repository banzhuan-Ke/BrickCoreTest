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

function applyRules(text, rules) {
  let result = text
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

const RULES = [
  {
    pattern: /suite_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-suite/${id}`
  },
  {
    pattern: /plan_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-plan/${id}`
  },
  {
    pattern: /api_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module?api_id=${id}`
  },
  {
    pattern: /case_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-case?case_id=${id}`
  },
  {
    pattern: /requirement_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/ai-requirements?requirement_id=${id}`
  },
  {
    pattern: /task_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/task/edit/${id}`
  },
  {
    pattern: /perf_scene_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-scene/edit/${id}`
  },
  {
    pattern: /perf_record_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-report/${id}`
  },
  {
    pattern: /target_id\s*=\s*(\d+)/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module/report/${id}`
  },
  {
    pattern: /(?:测试计划|API计划|接口计划)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-plan/${id}`
  },
  {
    pattern: /(?:压测场景|性能场景)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-scene/edit/${id}`
  },
  {
    pattern: /(?:压测记录|性能记录)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/perf-report/${id}`
  },
  {
    pattern: /(?:接口套件|API套件|套件)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-suite/${id}`
  },
  {
    pattern: /(?:接口定义|API接口|接口)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module?api_id=${id}`
  },
  {
    pattern: /(?:需求文档|需求)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/ai-requirements?requirement_id=${id}`
  },
  {
    pattern: /(?:UI计划|UI 计划|测试计划)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/task/edit/${id}`
  },
  {
    pattern: /(?:UI用例|Web用例|界面用例)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/case/edit/${id}`
  },
  {
    pattern: /(?:接口执行记录|执行记录)\s*[（(]?\s*id\s*=\s*(\d+)\s*[）)]?/gi,
    pickId: (a) => a[1],
    route: (id) => `#/api-module/report/${id}`
  }
]

function refineHashTags(text) {
  return text.split('\n').map((line) => {
    if (line.includes('](#/')) return line
    if (/需求/.test(line)) {
      return line.replace(/#\s*(\d+)/g, (m, id) => mdLink(m, `#/ai-requirements?requirement_id=${id}`))
    }
    if (/接口/.test(line) && /用例/.test(line)) {
      return line.replace(/#\s*(\d+)/g, (m, id) => mdLink(m, `#/api-case?api_id=${id}`))
    }
    if (/接口/.test(line)) {
      return line.replace(/#\s*(\d+)/g, (m, id) => mdLink(m, `#/api-module?api_id=${id}`))
    }
    if (/计划|task/i.test(line)) {
      return line.replace(/#\s*(\d+)/g, (m, id) => mdLink(m, `#/task/edit/${id}`))
    }
    if (/UI|用例/.test(line)) {
      return line.replace(/#\s*(\d+)/g, (m, id) => mdLink(m, `#/case/edit/${id}`))
    }
    return line
  }).join('\n')
}

export function linkifyAssistantContent(content) {
  if (!content) return ''
  let text = String(content)
  text = applyRules(text, RULES)
  text = refineHashTags(text)
  return text
}
