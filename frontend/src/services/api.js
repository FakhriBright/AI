const API_BASE_URL = 'http://172.16.204.27:8000'

export async function login(email, password) {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  })

  const data = await response.json()

  if (!response.ok) {
    throw new Error(data.detail || 'Login gagal')
  }

  return data
}

export async function getAnalysis(symbol, token) {
  const response = await fetch(
    `${API_BASE_URL}/analysis/${symbol}?count=300`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  )

  const data = await response.json()

  if (!response.ok) {
    throw new Error(data.detail || 'Gagal mengambil analysis')
  }

  return data
}
