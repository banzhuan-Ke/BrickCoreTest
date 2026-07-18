/**
 * CE stub：迭代资料库 API 开发测试中，后续放出。
 */
const unavailable = async () => {
  throw new Error('迭代资料库开发测试中，后续放出')
}

export const knowledgeApi = new Proxy(
  {},
  {
    get() {
      return unavailable
    },
  }
)

export default knowledgeApi
