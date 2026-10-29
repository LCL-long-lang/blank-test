import { Badge, Tooltip } from 'antd'
import { useBackendHealth } from '../../hooks/useBackendHealth'

/** 后端连接状态指示：已连接 / 连接中 / 未连接 */
export function BackendStatus() {
  const health = useBackendHealth()

  if (health.status === 'checking') {
    return <Badge status="processing" text="正在连接后端…" />
  }
  if (health.status === 'error') {
    return (
      <Tooltip title={health.message}>
        <Badge status="error" text="后端未连接" />
      </Tooltip>
    )
  }

  const { business_db, llm_configured, version } = health.data
  const warnings = [
    !business_db && '业务库未生成',
    !llm_configured && '未配置百炼 API Key',
  ].filter(Boolean)

  return (
    <Tooltip title={warnings.length ? warnings.join('；') : `后端 v${version}`}>
      <Badge status={warnings.length ? 'warning' : 'success'} text="后端已连接" />
    </Tooltip>
  )
}
