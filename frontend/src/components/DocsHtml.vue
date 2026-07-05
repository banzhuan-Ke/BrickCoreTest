<template>
  <div ref="rootRef" class="docs-html" v-html="html" />
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { BUILTIN_DOC_IDS } from '@/constants/docsBuiltin'

const props = defineProps({
  html: { type: String, default: '' }
})

const router = useRouter()
const rootRef = ref(null)

const html = computed(() => props.html || '<p class="empty">暂无内容</p>')

function parseDocNavigation(href) {
  if (!href) return null

  const docQuery = href.match(/\/docs\?doc=([a-z0-9-]+)(#.*)?$/i)
  if (docQuery) {
    return { docId: docQuery[1], hash: docQuery[2] || '' }
  }

  const mdMatch = href.match(/(?:^|[./\\])([a-z0-9-]+)\.md(#.*)?$/i)
  if (mdMatch) {
    const stem = mdMatch[1].toLowerCase()
    const docId = stem === 'index' ? 'home' : stem
    if (BUILTIN_DOC_IDS.has(docId)) {
      return { docId, hash: mdMatch[2] || '' }
    }
  }

  const hashMatch = href.match(/^#([a-z0-9-]+)$/i)
  if (hashMatch && BUILTIN_DOC_IDS.has(hashMatch[1])) {
    return { docId: hashMatch[1], hash: '' }
  }

  return null
}

function resolvePlatformPath(href) {
  if (href.startsWith('/#/')) return href.slice(2)
  if (href.startsWith('#/')) return href.slice(1)
  if (href.startsWith('/') && !href.startsWith('//') && !/\.[a-z]{2,4}(?:#|$)/i.test(href)) {
    const prefixes = [
      '/browser-lab', '/ai-', '/ui-', '/api-', '/perf-', '/project', '/app-',
      '/environment', '/docs', '/notification', '/dashboard', '/system'
    ]
    if (prefixes.some((p) => href.startsWith(p))) return href
  }
  return null
}

function onDocLinkClick(e) {
  const anchor = e.target.closest('a')
  if (!anchor || !rootRef.value?.contains(anchor)) return

  const href = anchor.getAttribute('href')
  if (!href || href.startsWith('javascript:')) return

  if (/^https?:\/\//i.test(href)) {
    if (!anchor.target) {
      e.preventDefault()
      window.open(href, '_blank', 'noopener')
    }
    return
  }

  const docNav = parseDocNavigation(href)
  if (docNav) {
    e.preventDefault()
    router.push({ path: '/docs', query: { doc: docNav.docId }, hash: docNav.hash })
    return
  }

  const platformPath = resolvePlatformPath(href)
  if (platformPath) {
    e.preventDefault()
    router.push(platformPath)
  }
}

watch(html, async () => {
  await nextTick()
  rootRef.value?.removeEventListener('click', onDocLinkClick)
  rootRef.value?.addEventListener('click', onDocLinkClick)
}, { immediate: true })
</script>

<style scoped>
.docs-html {
  font-size: 14px;
  line-height: 1.75;
  color: #303133;
  padding: 8px 4px 24px;
  word-break: break-word;
}

.docs-html :deep(h1) {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #409eff;
}

.docs-html :deep(h2) {
  font-size: 18px;
  font-weight: 600;
  margin: 24px 0 12px;
  padding-left: 10px;
  border-left: 4px solid #409eff;
}

.docs-html :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 16px 0 8px;
}

.docs-html :deep(p) { margin: 8px 0; }

.docs-html :deep(ul), .docs-html :deep(ol) {
  padding-left: 24px;
  margin: 8px 0 12px;
}

.docs-html :deep(li) { margin: 4px 0; }

.docs-html :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #c7254e;
}

.docs-html :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 14px 16px;
  border-radius: 8px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.5;
  margin: 12px 0;
}

.docs-html :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}

.docs-html :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.docs-html :deep(th), .docs-html :deep(td) {
  border: 1px solid #ebeef5;
  padding: 8px 12px;
  text-align: left;
}

.docs-html :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.docs-html :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.docs-html :deep(a:hover) { text-decoration: underline; }

.docs-html :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 4px solid #dcdfe6;
  background: #fafafa;
  color: #606266;
}

.docs-html :deep(.empty) {
  color: #909399;
  text-align: center;
  padding: 40px;
}
</style>
