import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom 缺少以下浏览器 API，antd（Splitter、响应式组件）依赖它们
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver

// 模拟 1440px 宽的桌面窗口：antd Grid.useBreakpoint 依赖 min-width / max-width 媒体查询
const VIEWPORT_WIDTH = 1440
function matchesQuery(query: string) {
  const min = /min-width:\s*(\d+)px/.exec(query)
  const max = /max-width:\s*(\d+(?:\.\d+)?)px/.exec(query)
  return (!min || VIEWPORT_WIDTH >= Number(min[1])) && (!max || VIEWPORT_WIDTH <= Number(max[1]))
}

Element.prototype.scrollTo ??= function scrollTo() {}

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: matchesQuery(query),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})
