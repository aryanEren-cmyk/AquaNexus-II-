const API_BASE_URL = import.meta.env.VITE_AQUANEXUS_API_URL || 'http://127.0.0.1:8000'

export async function getHealth() {
  return request('/api/health')
}

export async function sendChatMessage(message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}

export async function getOceanConditions(location, depth_m = 0, argo_radius_km = 300) {
  return request('/api/ocean/conditions', {
    method: 'POST',
    body: JSON.stringify({
      location,
      depth_m,
      argo_radius_km,
    }),
  })
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  let payload = null
  try {
    payload = await response.json()
  } catch {
    // Some successful responses may not include a JSON body.
  }

  if (!response.ok) {
    const message =
      payload?.detail?.message ||
      payload?.detail ||
      `Backend request failed with HTTP ${response.status}`
    throw new Error(typeof message === 'string' ? message : 'Backend request failed')
  }

  return payload
}
