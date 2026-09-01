/**
 * Next.js instrumentation hook for CivicPulse.
 *
 * Loads the New Relic Node.js agent (Hybrid Agent) ONLY when a real license
 * key is present. Without a key this is a no-op, so local dev, CI and the
 * production build are unaffected.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') {
    return
  }

  if (!process.env.NEW_RELIC_LICENSE_KEY) {
    return
  }

  const { default: newrelic } = await import('newrelic')
  await loadNewRelicAgent(newrelic)
}

async function loadNewRelicAgent(newrelic: { agent: NewRelicAgent }) {
  const agent = newrelic?.agent
  if (!agent || agent.collector?.isConnected?.()) {
    return newrelic
  }

  await new Promise<void>((resolve) => {
    let settled = false
    const done = () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      agent.removeListener('started', done)
      agent.removeListener('errored', done)
      resolve()
    }
    const timer = setTimeout(done, 8000)
    agent.once('started', done)
    agent.once('errored', done)
  })

  return newrelic
}

interface NewRelicAgent {
  collector: {
    isConnected?: () => boolean
  }
  removeListener: (event: string, listener: () => void) => void
  once: (event: string, listener: () => void) => void
}
