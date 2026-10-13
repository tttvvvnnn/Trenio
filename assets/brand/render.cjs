// Экспортирует PNG из SVG логотипа через Playwright (Chromium).
// Запуск из корня репозитория: node assets/brand/render.cjs
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const brand = __dirname
const pub = path.join(brand, '..', '..', 'frontend', 'public')
const jobs = [
  ['bot-avatar.svg', path.join(brand, 'bot-avatar.png'), 640, 640],
  ['bot-description.svg', path.join(brand, 'bot-description.png'), 640, 360],
  ['app-icon.svg', path.join(brand, 'app-icon.png'), 1024, 1024],
  ['app-icon.svg', path.join(pub, 'apple-touch-icon.png'), 180, 180],
]

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  for (const [src, dst, width, height] of jobs) {
    const svg = fs.readFileSync(path.join(brand, src), 'utf8')
    await page.setViewportSize({ width, height })
    await page.setContent(
      `<body style="margin:0">${svg.replace('<svg ', `<svg width="${width}" height="${height}" `)}</body>`,
    )
    await page.screenshot({ path: dst, clip: { x: 0, y: 0, width, height } })
    console.log(path.relative(process.cwd(), dst))
  }
  await browser.close()
})()
