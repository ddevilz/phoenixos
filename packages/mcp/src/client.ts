const CORE_API = process.env.PHOENIX_API_URL ?? "http://localhost:8000";

export async function coreGet<T>(path: string): Promise<T> {
  const res = await fetch(`${CORE_API}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} → ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function corePost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${CORE_API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${path} → ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
