const CORE_API = process.env.PHOENIX_API_URL ?? "http://localhost:8000";
export async function coreGet(path) {
    const res = await fetch(`${CORE_API}${path}`);
    if (!res.ok) {
        throw new Error(`GET ${path} → ${res.status} ${res.statusText}`);
    }
    return res.json();
}
export async function corePost(path, body) {
    const res = await fetch(`${CORE_API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        throw new Error(`POST ${path} → ${res.status} ${res.statusText}`);
    }
    return res.json();
}
