/** 对应 backend/app/common/schemas.py 的会话模型 */
export interface Session {
  id: string
  title: string
  pinned: boolean
  created_at: string
  updated_at: string
}

export interface SessionCreate {
  title?: string
}

export interface SessionUpdate {
  title?: string
  pinned?: boolean
}
