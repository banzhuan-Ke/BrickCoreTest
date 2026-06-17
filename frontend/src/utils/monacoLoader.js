/** Monaco 按需加载：仅 editor.api + SQL 语法，避免打入全量语言包 */
let monacoPromise = null

export function loadMonaco() {
  if (!monacoPromise) {
    monacoPromise = (async () => {
      const { default: EditorWorker } = await import(
        'monaco-editor/esm/vs/editor/editor.worker?worker'
      )
      self.MonacoEnvironment = {
        getWorker() {
          return new EditorWorker()
        },
      }
      const monaco = await import('monaco-editor/esm/vs/editor/editor.api')
      await import('monaco-editor/esm/vs/basic-languages/sql/sql.contribution')
      return monaco
    })()
  }
  return monacoPromise
}
