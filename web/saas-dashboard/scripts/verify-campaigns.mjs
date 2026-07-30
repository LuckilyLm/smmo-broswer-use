import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const baseUrl = process.env.SAAS_DASHBOARD_URL || 'http://127.0.0.1:8080'
const session = process.env.LEADFLOW_SESSION || ''
const outputDir = path.resolve(process.env.CAMPAIGNS_VERIFY_OUTPUT_DIR || 'output/playwright')
const base = new URL(baseUrl)

if (!session) {
  console.error('LEADFLOW_SESSION is required. Set it to a signed leadflow_session cookie value.')
  process.exit(2)
}

fs.mkdirSync(outputDir, { recursive: true })

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true })
  } catch (error) {
    const chromePaths = [
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    ]
    const executablePath = chromePaths.find((candidate) => fs.existsSync(candidate))
    if (!executablePath) throw error
    return chromium.launch({ headless: true, executablePath })
  }
}

const browser = await launchBrowser()
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
await context.addCookies([
  {
    name: 'leadflow_session',
    value: session,
    domain: base.hostname,
    path: '/',
    httpOnly: true,
    sameSite: 'Lax',
  },
])

const page = await context.newPage()
const errors = []
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text())
})
page.on('pageerror', (error) => errors.push(error.message))

await page.goto(`${baseUrl}/campaigns`, { waitUntil: 'networkidle', timeout: 30000 })
await page.screenshot({ path: path.join(outputDir, 'campaigns-desktop.png'), fullPage: true })

const desktop = {
  url: page.url(),
  title: await page.locator('h1').first().textContent(),
  keywordHeaderCount: await page.getByRole('columnheader', { name: '关键词' }).count(),
  replyModeHeaderCount: await page.getByRole('columnheader', { name: '回复模式' }).count(),
  detailsButtons: await page.getByRole('button', { name: /查看详情/ }).count(),
  editButtons: await page.getByRole('button', { name: /编辑设置/ }).count(),
  runButtons: await page.getByRole('button', { name: /运行一次/ }).count(),
  toggleButtons: await page.getByRole('button', { name: /暂停活动|启用活动/ }).count(),
  deleteButtons: await page.getByRole('button', { name: /删除/ }).count(),
}

if (desktop.detailsButtons > 0) {
  await page.getByRole('button', { name: /查看详情/ }).first().click()
  await page.getByRole('dialog').waitFor({ timeout: 10000 })
  await page.screenshot({ path: path.join(outputDir, 'campaigns-detail-desktop.png'), fullPage: true })
}

const modal = {
  dialogCount: await page.getByRole('dialog').count(),
  executionConfigCount: await page.getByText('执行配置').count(),
  replyConfigCount: await page.getByText('回复配置').count(),
  internalEnglishStatusCount: await page.getByText(/manual_approval|discovery_only|rules_with_llm|pending_approval/).count(),
}

if (modal.dialogCount > 0) {
  await page.getByRole('dialog').getByRole('button', { name: '关闭详情' }).click()
}

for (const width of [390, 430, 768]) {
  await page.setViewportSize({ width, height: 844 })
  await page.goto(`${baseUrl}/campaigns`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.screenshot({ path: path.join(outputDir, `campaigns-mobile-${width}.png`), fullPage: true })
}

const mobile = {
  bodyScrollWidth: await page.evaluate(() => document.body.scrollWidth),
  viewportWidth: await page.evaluate(() => window.innerWidth),
  detailsButtons: await page.getByRole('button', { name: /查看详情/ }).count(),
  runButtons: await page.getByRole('button', { name: /运行一次/ }).count(),
  editButtons: await page.getByRole('button', { name: /编辑设置/ }).count(),
  deleteButtons: await page.getByRole('button', { name: /删除/ }).count(),
}

const result = { desktop, modal, mobile, errors }
fs.writeFileSync(path.join(outputDir, 'campaigns-verify.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf-8')

await browser.close()

const failures = []
if (desktop.keywordHeaderCount || desktop.replyModeHeaderCount) failures.push('compact table contains moved detail columns')
for (const [key, value] of Object.entries({
  detailsButtons: desktop.detailsButtons,
  editButtons: desktop.editButtons,
  runButtons: desktop.runButtons,
  toggleButtons: desktop.toggleButtons,
  deleteButtons: desktop.deleteButtons,
})) {
  if (!value) failures.push(`missing desktop action: ${key}`)
}
if (!modal.dialogCount || !modal.executionConfigCount || !modal.replyConfigCount) failures.push('detail modal is incomplete')
if (modal.internalEnglishStatusCount) failures.push('detail modal exposes internal English status values')
if (mobile.bodyScrollWidth > mobile.viewportWidth + 2) failures.push('mobile horizontal overflow detected')
if (errors.length) failures.push(`console errors: ${errors.length}`)

console.log(JSON.stringify(result, null, 2))
if (failures.length) {
  console.error(`Campaigns verification failed: ${failures.join('; ')}`)
  process.exit(1)
}
