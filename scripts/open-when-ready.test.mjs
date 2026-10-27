import assert from 'node:assert/strict'
import { test } from 'node:test'
import { openWhenReady } from './open-when-ready.mjs'

const noWait = async () => {}

test('the browser opens only once the portal answers', async () => {
  const answers = [false, false, true]
  const opened = []
  const ready = await openWhenReady({
    check: async () => answers.shift(),
    open: (url) => opened.push(url),
    wait: noWait,
    url: 'http://127.0.0.1:9080',
    attempts: 10,
  })
  assert.equal(ready, true)
  assert.deepEqual(answers, [])
  assert.deepEqual(opened, ['http://127.0.0.1:9080'])
})

test('a check that fails outright counts as not ready yet', async () => {
  let calls = 0
  const opened = []
  await openWhenReady({
    check: async () => {
      calls += 1
      if (calls === 1) throw new Error('ECONNREFUSED')
      return true
    },
    open: (url) => opened.push(url),
    wait: noWait,
    url: 'http://x',
    attempts: 10,
  })
  assert.equal(calls, 2)
  assert.deepEqual(opened, ['http://x'])
})

test('a portal that never answers is not opened', async () => {
  const opened = []
  const ready = await openWhenReady({
    check: async () => false,
    open: (url) => opened.push(url),
    wait: noWait,
    url: 'http://x',
    attempts: 3,
  })
  assert.equal(ready, false)
  assert.deepEqual(opened, [])
})
