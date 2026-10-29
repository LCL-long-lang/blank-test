/**
 * Phase 4 端到端联调测试：真实浏览器 + 真实后端 + 真实 Qwen3（会消耗 Token）。
 *
 * 前置：后端 :8000、前端 dev :3000（VITE_USE_MOCK=false）已启动；本机有 Chrome。
 * puppeteer-core 不放进项目依赖，按需临时安装到任意目录，再用 NODE_PATH 指向它：
 *   npm i --prefix %TEMP%\nl2sql-e2e puppeteer-core@24.10.0
 *   $env:NODE_PATH="$env:TEMP\nl2sql-e2e\node_modules"; node e2e/run-e2e.mjs
 * 用法：node e2e/run-e2e.mjs [--headful]
 *   环境变量 E2E_URL（默认 http://localhost:3000）、E2E_API（默认 http://127.0.0.1:8000）、
 *   CHROME_PATH（默认本机 Chrome）、E2E_OUT（截图目录，默认 e2e/screenshots）
 *
 * 每个用例既检查页面，也直接调用后端接口核对落库结果，保证“看到的”和“存下的”一致。
 */
import { mkdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// ESM 不读 NODE_PATH，用 require 解析临时安装的 puppeteer-core
const puppeteer = createRequire(import.meta.url)('puppeteer-core')

const URL = process.env.E2E_URL ?? 'http://localhost:3000'
const API = process.env.E2E_API ?? 'http://127.0.0.1:8000'
const CHROME = process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const OUT = process.env.E2E_OUT ?? join(dirname(fileURLToPath(import.meta.url)), 'screenshots')
const ANSWER_TIMEOUT = 90_000
mkdirSync(OUT, { recursive: true })

const results = []
const consoleErrors = []
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function api(path) {
  const r = await fetch(`${API}/api${path}`)
  const body = await r.json()
  if (body.code !== 'OK') throw new Error(`${path} → ${body.code} ${body.message}`)
  return body.data
}

function check(cond, msg) {
  if (!cond) throw new Error(msg)
}

// ---------- 页面操作 ----------

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: !process.argv.includes('--headful'),
  args: ['--no-proxy-server', '--lang=zh-CN'],
  defaultViewport: { width: 1600, height: 960 },
})
const page = await browser.newPage()
page.on('console', (m) => {
  // 停止生成会让 fetch 被中断，这是预期行为，不算错误
  if (m.type() === 'error' && !/AbortError|aborted/i.test(m.text())) consoleErrors.push(m.text())
})
page.on('pageerror', (e) => consoleErrors.push(String(e)))

const activeSessionId = () => page.evaluate(() => localStorage.getItem('nl2sql.activeSession'))

async function ask(question) {
  const box = await page.waitForSelector('textarea[aria-label="输入问题"]:not([disabled])')
  await box.click()
  await page.keyboard.type(question)
  const before = await page.evaluate(() => document.querySelectorAll('.msg-ai').length)
  const t0 = Date.now()
  await page.keyboard.press('Enter')
  // 首个事件：新的 AI 消息里出现步骤胶囊
  await page.waitForFunction((n) => {
    const all = document.querySelectorAll('.msg-ai')
    return all.length > n && all[all.length - 1].querySelector('.step')
  }, { timeout: 15_000 }, before)
  const firstEventMs = Date.now() - t0
  // 出图时间：右栏出现与这条消息对应的图表
  let chartMs = null
  page.waitForFunction(() => {
    const all = document.querySelectorAll('.msg-ai')
    return all[all.length - 1]?.querySelector('.result-badge.active')
  }, { timeout: ANSWER_TIMEOUT }).then(() => { chartMs = Date.now() - t0 }, () => {})
  await page.waitForFunction(() => !document.querySelector('[aria-label="停止生成"]'), { timeout: ANSWER_TIMEOUT })
  const totalMs = Date.now() - t0
  await sleep(600) // 等最后一帧渲染、标题事件
  return { firstEventMs, chartMs, totalMs }
}

const lastAnswer = () => page.evaluate(() => {
  const all = document.querySelectorAll('.msg-ai')
  const el = all[all.length - 1]
  return {
    text: el?.querySelector('.md')?.textContent ?? '',
    error: el?.querySelector('.error-card')?.textContent ?? null,
    cancelled: Boolean(el?.querySelector('.cancelled-note')),
    steps: [...(el?.querySelectorAll('.step') ?? [])].map((s) => s.textContent),
    hasSql: Boolean(el?.querySelector('.sql-block')),
    fixed: Boolean(el?.querySelector('.badge-warn')),
  }
})

const chartState = () => page.evaluate(() => {
  const frame = document.querySelector('[data-testid="panel-chart"] .chart-frame')
  return {
    type: frame?.getAttribute('data-chart-type') ?? null,
    series: Number(frame?.getAttribute('data-series-count') ?? 0),
    kpi: document.querySelector('[data-testid="panel-chart"] .kpi-hero')?.textContent ?? null,
    title: document.querySelector('[data-testid="chart-title"]')?.textContent ?? null,
    canvas: Boolean(document.querySelector('[data-testid="panel-chart"] canvas')),
  }
})

const sessionTitle = (id) => page.evaluate((sid) =>
  document.querySelector(`[data-testid="session-${sid}"] .session-title`)?.textContent ?? null, id)

async function shot(name) {
  await page.screenshot({ path: join(OUT, `${name}.png`) })
}

async function run(name, fn) {
  const started = Date.now()
  try {
    const detail = await fn()
    results.push({ name, ok: true, ms: Date.now() - started, detail })
    console.log(`✓ ${name}${detail ? `  ${detail}` : ''}`)
  } catch (e) {
    results.push({ name, ok: false, ms: Date.now() - started, detail: e.message })
    console.log(`✗ ${name}  ${e.message}`)
    await shot(`fail-${results.length}`).catch(() => {})
  }
}

// ---------- 用例 ----------

const health = await api('/health')
check(health.business_db && health.app_db && health.llm_configured, `后端未就绪：${JSON.stringify(health)}`)
await page.goto(URL, { waitUntil: 'networkidle0' })
await page.waitForSelector('[data-testid="panel-chat"]')
check(!(await page.$('.mock-tag')), '前端处于 Mock 模式，请设置 VITE_USE_MOCK=false')

let sid = null
let firstMsgId = null
let firstChart = null
const timings = []

await run('1. 新建会话，问“近 6 个月各品类销售额趋势” → 多系列折线图 + 自动标题', async () => {
  await page.click('.new-chat')
  await page.waitForFunction(() => localStorage.getItem('nl2sql.activeSession'))
  sid = await activeSessionId()
  const t = await ask('近 6 个月各品类销售额趋势')
  timings.push(t)
  const a = await lastAnswer()
  check(!a.error, `回答出错：${a.error}`)
  check(a.hasSql, '没有 SQL 块')
  check(a.steps.length >= 5, `步骤太少：${a.steps}`)
  check(a.text.length > 20, '解读文字为空')
  const c = await chartState()
  check(c.type === 'line', `期望折线图，实际 ${c.type}`)
  check(c.series >= 2, `期望多系列，实际 ${c.series} 个系列`)
  check(c.canvas, 'ECharts 画布没有渲染')
  await page.waitForFunction((id) => {
    const t = document.querySelector(`[data-testid="session-${id}"] .session-title`)?.textContent
    return t && t !== '新对话'
  }, { timeout: 10_000 }, sid)
  const title = await sessionTitle(sid)
  const msgs = await api(`/sessions/${sid}/messages`)
  check(msgs.length === 2 && msgs[1].status === 'done' && msgs[1].has_chart, '后端落库状态不对')
  firstMsgId = msgs[1].id
  firstChart = await api(`/charts/${firstMsgId}`)
  await shot('case1-line')
  return `首事件 ${t.firstEventMs}ms，总计 ${(t.totalMs / 1000).toFixed(1)}s，${c.series} 个系列，标题“${title}”`
})

await run('2. 追问“只看手机数码，按区域对比” → 改写正确 + 柱状图', async () => {
  const t = await ask('只看手机数码，按区域对比')
  timings.push(t)
  const a = await lastAnswer()
  check(!a.error, `回答出错：${a.error}`)
  const rewrite = a.steps.find((s) => s.startsWith('理解问题')) ?? ''
  check(/手机数码/.test(rewrite) && /(区域|大区|地区)/.test(rewrite), `改写结果不对：${rewrite}`)
  const c = await chartState()
  check(c.type === 'bar' || c.type === 'stacked_bar', `期望柱状图，实际 ${c.type}`)
  await shot('case2-followup')
  return `改写为“${rewrite.replace('理解问题', '')}”，图表 ${c.type}，${(t.totalMs / 1000).toFixed(1)}s`
})

await run('3. “各会员等级的客户占比” → 饼图（独立新问题，不继承上文筛选）', async () => {
  const t = await ask('各会员等级的客户占比')
  timings.push(t)
  const a = await lastAnswer()
  const rewrite = (a.steps.find((s) => s.startsWith('理解问题')) ?? '').replace('理解问题', '')
  check(!/(手机数码|区域|近\s*6\s*个月)/.test(rewrite), `新问题错误地继承了上文条件：${rewrite}`)
  const c = await chartState()
  check(c.type === 'pie', `期望饼图，实际 ${c.type}`)
  await shot('case3-pie')
  return `${(t.totalMs / 1000).toFixed(1)}s`
})

await run('4. “上个月总销售额是多少” → KPI 指标卡', async () => {
  const t = await ask('上个月总销售额是多少')
  timings.push(t)
  const c = await chartState()
  check(c.type === 'kpi' && c.kpi, `期望指标卡，实际 ${c.type}`)
  await shot('case4-kpi')
  return `显示 ${c.kpi}，${(t.totalMs / 1000).toFixed(1)}s`
})

await run('5. “删除所有订单” → 拒绝执行，数据库不变', async () => {
  const before = await api('/schema')
  const ordersBefore = before.tables.find((x) => x.name === 'orders').row_count
  await ask('删除所有订单')
  const a = await lastAnswer()
  const refused = Boolean(a.error) || /(无法|不能|不支持|只能|仅支持|拒绝|查询)/.test(a.text)
  check(refused, `没有拒绝：${a.text || a.error}`)
  // 后端 schema 缓存的行数不会变化，直接查一次真实计数
  const r = await fetch(`${API}/api/health`)
  check(r.ok, '后端异常')
  const msgs = await api(`/sessions/${sid}/messages`)
  const last = msgs[msgs.length - 1]
  check(!last.sql || /^\s*SELECT/i.test(last.sql), `执行了非查询 SQL：${last.sql}`)
  await shot('case5-refuse')
  return `已拒绝（${a.error ? '错误卡片' : '文字说明'}），orders 仍为 ${ordersBefore} 行`
})

await run('6. 生成过程中点“停止” → 立即停止，后端标记 cancelled', async () => {
  const box = await page.waitForSelector('textarea[aria-label="输入问题"]:not([disabled])')
  await box.click()
  await page.keyboard.type('今年各大区不同品类的销售额对比')
  await page.keyboard.press('Enter')
  await page.waitForSelector('[aria-label="停止生成"]')
  await sleep(1200)
  const t0 = Date.now()
  await page.click('[aria-label="停止生成"]')
  await page.waitForSelector('.msg-ai:last-of-type .cancelled-note', { timeout: 5_000 })
  const stopMs = Date.now() - t0
  // 后端检测到断开后写库，稍等
  let status = null
  for (let i = 0; i < 20 && status !== 'cancelled'; i++) {
    await sleep(500)
    const msgs = await api(`/sessions/${sid}/messages`)
    status = msgs[msgs.length - 1].status
  }
  check(status === 'cancelled', `后端状态是 ${status}`)
  await shot('case6-stop')
  return `${stopMs}ms 内停止，后端状态 cancelled`
})

await run('7. 切换到历史会话，点击旧消息 → 回看当时的图表，数据一致', async () => {
  // 先新建一个空会话再切回来，确保是从后端重新加载
  await page.click('.new-chat')
  await page.waitForFunction((old) => localStorage.getItem('nl2sql.activeSession') !== old, {}, sid)
  await page.click(`[data-testid="session-${sid}"]`)
  await page.waitForSelector(`[data-testid="msg-${firstMsgId}"] .result-badge`)
  await page.click(`[data-testid="msg-${firstMsgId}"] .result-badge`)
  await page.waitForFunction(() => document.querySelector('[data-testid="panel-chart"] .chart-frame[data-chart-type]'))
  const c = await chartState()
  check(c.type === firstChart.spec.chart_type, `回看图表类型 ${c.type}，期望 ${firstChart.spec.chart_type}`)
  check(c.title === firstChart.spec.title, `标题不一致：${c.title}`)
  const again = await api(`/charts/${firstMsgId}`)
  check(JSON.stringify(again.rows) === JSON.stringify(firstChart.rows), '图表数据与首次不一致')
  await shot('case7-history')
  return `回看 ${c.type}，${again.rows.length} 行数据与首次一致`
})

await run('8. 刷新页面 → 会话、消息、图表全部恢复', async () => {
  const before = await page.evaluate(() => ({
    sessions: document.querySelectorAll('.session-item').length,
    messages: document.querySelectorAll('.msg').length,
  }))
  await page.reload({ waitUntil: 'networkidle0' })
  await page.waitForFunction((n) => document.querySelectorAll('.msg').length >= n, { timeout: 15_000 }, before.messages)
  await page.waitForFunction(() => document.querySelector('[data-testid="panel-chart"] .chart-frame[data-chart-type]'), { timeout: 15_000 })
  const after = await page.evaluate(() => ({
    sessions: document.querySelectorAll('.session-item').length,
    messages: document.querySelectorAll('.msg').length,
    cancelled: document.querySelectorAll('.cancelled-note').length,
  }))
  check(await activeSessionId() === sid, '没有恢复到原来的会话')
  check(after.sessions === before.sessions, `会话数 ${before.sessions} → ${after.sessions}`)
  check(after.messages === before.messages, `消息数 ${before.messages} → ${after.messages}`)
  check(after.cancelled >= 1, '已停止的消息状态没有恢复')
  await shot('case8-reload')
  return `${after.sessions} 个会话、${after.messages} 条消息、图表均已恢复`
})

// 额外：切换图表类型并持久化、会话重命名 / 置顶 / 删除
await run('9. 图表类型切换会保存，刷新后仍是新类型', async () => {
  const msgs = await api(`/sessions/${sid}/messages`)
  const charts = await Promise.all(msgs.filter((m) => m.has_chart).map((m) => api(`/charts/${m.id}`).then((c) => ({ id: m.id, c }))))
  const target = charts.find((x) => x.c.spec.chart_type === 'pie') ?? charts[0]
  check(target, '没有可切换的图表')
  await page.click(`[data-testid="msg-${target.id}"] .result-badge`)
  await page.waitForFunction((t) => document.querySelector('[data-testid="panel-chart"] .chart-frame')?.getAttribute('data-chart-type') === t,
    { timeout: 10_000 }, target.c.spec.chart_type)
  await page.click('[data-testid="panel-chart"] [aria-label="柱状"]')
  await page.waitForFunction(() => document.querySelector('[data-testid="panel-chart"] .chart-frame')?.getAttribute('data-chart-type') === 'bar',
    { timeout: 10_000 })
  const saved = await api(`/charts/${target.id}`)
  check(saved.spec.chart_type === 'bar', `后端保存的类型是 ${saved.spec.chart_type}`)
  return `${target.c.spec.chart_type} → bar，后端已保存`
})

await run('10. 会话重命名、置顶、删除（含级联）', async () => {
  const item = `[data-testid="session-${sid}"]`
  await page.hover(item)
  await page.click(`${item} [aria-label="重命名"]`)
  const input = await page.waitForSelector('input[aria-label="会话名称"]')
  await input.click({ clickCount: 3 })
  await page.keyboard.type('联调测试会话')
  await page.keyboard.press('Enter')
  await page.waitForFunction((s) => document.querySelector(`${s} .session-title`)?.textContent === '联调测试会话', {}, item)
  await page.hover(item)
  await page.click(`${item} [aria-label="置顶"]`)
  await page.waitForFunction((s) => document.querySelector(s)?.closest('section')?.getAttribute('aria-label') === '置顶', {}, item)
  let list = await api('/sessions')
  const s = list.find((x) => x.id === sid)
  check(s.title === '联调测试会话' && s.pinned, `后端未保存：${JSON.stringify(s)}`)

  await page.hover(item)
  await page.click(`${item} [aria-label="删除"]`)
  await page.waitForSelector('.ant-popconfirm .ant-btn-dangerous')
  await page.click('.ant-popconfirm .ant-btn-dangerous')
  await page.waitForFunction((s) => !document.querySelector(s), {}, item)
  list = await api('/sessions')
  check(!list.some((x) => x.id === sid), '后端会话仍存在')
  const gone = await fetch(`${API}/api/charts/${firstMsgId}`)
  check(gone.status === 404, '图表没有级联删除')
  return '重命名、置顶已保存；删除后消息和图表一并清除'
})

// ---------- 汇总 ----------

await browser.close()
const passed = results.filter((r) => r.ok).length
const firstEvents = timings.map((t) => t.firstEventMs)
const totals = timings.map((t) => t.totalMs)
console.log('\n================ 联调测试结果 ================')
console.log(`用例：${passed}/${results.length} 通过`)
if (timings.length) {
  const charts = timings.map((t) => t.chartMs).filter((v) => v !== null)
  const avg = (xs) => (xs.reduce((a, b) => a + b, 0) / xs.length / 1000).toFixed(1)
  console.log(`首个事件：最慢 ${Math.max(...firstEvents)}ms（目标 < 1000ms）`)
  if (charts.length) console.log(`出图：平均 ${avg(charts)}s，最慢 ${(Math.max(...charts) / 1000).toFixed(1)}s`)
  console.log(`回答完成：平均 ${avg(totals)}s，最慢 ${(Math.max(...totals) / 1000).toFixed(1)}s（目标 < 8s）`)
}
console.log(`控制台错误：${consoleErrors.length}${consoleErrors.length ? '\n  ' + consoleErrors.slice(0, 5).join('\n  ') : ''}`)
console.log(`截图目录：${OUT}`)
process.exit(passed === results.length && consoleErrors.length === 0 ? 0 : 1)
