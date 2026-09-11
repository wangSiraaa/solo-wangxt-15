const BASE = '/api'

async function req(path, options = {}) {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    const err = new Error(data.detail || `请求失败 (${resp.status})`)
    err.status = resp.status
    err.data = data
    throw err
  }
  return data
}

export const api = {
  products: () => req('/products/'),
  materials: () => req('/materials/'),
  versions: () => req('/versions/'),
  version: (id) => req(`/versions/${id}/`),
  versionTree: (id) => req(`/versions/${id}/tree/`),
  validate: (id) => req(`/versions/${id}/validate/`),
  publish: (id) => req(`/versions/${id}/publish/`, { method: 'POST' }),
  compare: (from, to) => req(`/compare/?from=${from}&to=${to}`),
  rules: (versionId) => req(`/rules/?version=${versionId}`),
  createRule: (payload) => req('/rules/', { method: 'POST', body: JSON.stringify(payload) }),
  deleteRule: (id) => req(`/rules/${id}/`, { method: 'DELETE' }),
  resolve: (product, serial) => req(`/resolve/?product=${encodeURIComponent(product)}&serial=${serial}`),
  issue: (payload) => req('/issue/', { method: 'POST', body: JSON.stringify(payload) }),
  issues: (product) => req(`/issues/${product ? '?product=' + encodeURIComponent(product) : ''}`),
}
