import { useEffect, useState } from 'react'
import { api } from '../services'
import type { HealthOut } from '../types'

export type HealthState =
  | { status: 'checking' }
  | { status: 'ok'; data: HealthOut }
  | { status: 'error'; message: string }

/** 启动时检查后端连通性，用于页面角落的连接状态 */
export function useBackendHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ status: 'checking' })

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then((data) => !cancelled && setState({ status: 'ok', data }))
      .catch((err: Error) => !cancelled && setState({ status: 'error', message: err.message }))
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
