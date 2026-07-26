import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../src/components/Layout.tsx', import.meta.url), 'utf8')

test('core 识境 navigation pages are mounted', () => {
  const routes = [
    'identify',
    'video',
    'jobs',
    'species',
    'map',
    'alerts',
    'qa',
    'review',
    'history',
    'analytics',
    'models',
    'datasets',
    'reports',
    'settings',
  ]
  for (const route of routes) {
    assert.match(app, new RegExp(`path="${route}"`))
  }
})

test('navigation labels match the product acceptance surface', () => {
  const labels = [
    '综合态势',
    '图片识别',
    '视频识别',
    '分析任务',
    '物种百科',
    '生态图谱',
    '风险事件',
    '智能科普',
    '人工复核',
    '观察记录',
    '数据分析',
    '模型中心',
    '数据集管理',
    'AI报告',
    '系统设置',
  ]
  for (const label of labels) {
    assert.ok(layout.includes(label), `missing nav label: ${label}`)
  }
})
