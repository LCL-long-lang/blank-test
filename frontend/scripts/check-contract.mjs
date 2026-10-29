/**
 * 契约核对：后端 /openapi.json 的模型字段 vs 前端 src/types 的接口字段。
 * 用法：node scripts/check-contract.mjs [http://127.0.0.1:8000]
 * 只比较字段名集合（类型由各自的测试保证），任何一边多出或缺少字段都会报错并以非 0 退出。
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const base = process.argv[2] ?? 'http://127.0.0.1:8000'
const typesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'types')

// 后端模型名 → 前端接口名（同名的不用写）
const PAIRS = {
  SessionOut: 'Session',
  SessionUpdate: 'SessionUpdate',
  MessageOut: 'MessageOut',
  ChartSpec: 'ChartSpec',
  ChartOut: 'ChartOut',
  ChartRenderRequest: 'ChartRenderRequest',
  ChatRequest: 'ChatRequest',
  HealthOut: 'HealthOut',
  SchemaOut: 'SchemaOut',
  SchemaTableOut: 'SchemaTable',
  SchemaColumnOut: 'SchemaColumn',
}

/** 解析 TS 文件中 `export interface X { a: ...; b?: ... }` 的字段名 */
function tsInterfaces() {
  const files = ['session.ts', 'message.ts', 'chart.ts', 'common.ts', 'schema.ts', 'sse.ts']
  const out = {}
  for (const f of files) {
    const src = readFileSync(join(typesDir, f), 'utf8')
    for (const m of src.matchAll(/export interface (\w+)(?:<[^>]+>)?\s*\{([\s\S]*?)\n\}/g)) {
      out[m[1]] = new Set([...m[2].matchAll(/^\s*(\w+)\??:/gm)].map((x) => x[1]))
    }
  }
  return out
}

const resp = await fetch(`${base}/openapi.json`)
if (!resp.ok) {
  console.error(`无法获取 ${base}/openapi.json：HTTP ${resp.status}`)
  process.exit(2)
}
const schemas = (await resp.json()).components.schemas
const ts = tsInterfaces()
let failed = 0

for (const [py, tsName] of Object.entries(PAIRS)) {
  const back = new Set(Object.keys(schemas[py]?.properties ?? {}))
  const front = ts[tsName]
  if (!schemas[py] || !front) {
    console.log(`✗ ${py} ↔ ${tsName}：${!schemas[py] ? '后端' : '前端'}找不到该模型`)
    failed++
    continue
  }
  const onlyBack = [...back].filter((k) => !front.has(k))
  const onlyFront = [...front].filter((k) => !back.has(k))
  if (onlyBack.length || onlyFront.length) {
    failed++
    console.log(`✗ ${py} ↔ ${tsName}  后端独有：[${onlyBack}]  前端独有：[${onlyFront}]`)
  } else {
    console.log(`✓ ${py} ↔ ${tsName}（${back.size} 个字段）`)
  }
}

// SSE 事件不在 openapi 中：与后端 schemas.py 的 SSE_EVENT_MODELS 对照（事件名固定）
const SSE = ['start', 'step', 'sql', 'data', 'chart', 'text', 'title', 'error', 'done']
const mapBody = /export interface SSEEventMap \{([\s\S]*?)\n\}/.exec(readFileSync(join(typesDir, 'sse.ts'), 'utf8'))[1]
const frontEvents = [...mapBody.matchAll(/^\s*(\w+):/gm)].map((m) => m[1])
const missing = SSE.filter((e) => !frontEvents.includes(e))
console.log(missing.length ? `✗ SSE 事件缺少：${missing}` : `✓ SSE 事件 ${SSE.length} 种一致`)
if (missing.length) failed++

console.log(failed ? `\n契约不一致：${failed} 处` : '\n契约一致')
process.exit(failed ? 1 : 0)
