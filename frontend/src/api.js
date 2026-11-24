async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`Request failed (${res.status}) for ${url}`);
  return res.json();
}

export const api = {
  summary: () => request("/api/summary"),
  daily: () => request("/api/costs/daily"),
  breakdown: (by) => request(`/api/costs/breakdown?by=${by}`),
  recommendations: () => request("/api/recommendations"),
  resources: () => request("/api/resources"),
  analyze: () => request("/api/analyze", { method: "POST" }),
  reseed: () => request("/api/seed", { method: "POST" }),
};
