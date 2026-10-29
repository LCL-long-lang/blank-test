/** 服务层唯一出口：按 VITE_USE_MOCK 选择真实接口或 Mock，store 与组件只从这里导入 */
import { mockApi, mockStreamChat } from '../mocks'
import { realApi, type ApiClient } from './api'
import { realStreamChat, type StreamChat } from './sse'

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export const api: ApiClient = USE_MOCK ? mockApi : realApi
export const streamChat: StreamChat = USE_MOCK ? mockStreamChat : realStreamChat

export { ApiError } from './http'
export type { ApiClient } from './api'
export type { StreamChat, StreamHandlers } from './sse'
