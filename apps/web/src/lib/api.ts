export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(code);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers,
  });
  if (!response.ok) {
    let code = `HTTP_${response.status}`;
    try {
      const payload = await response.json() as {
        error?: { code?: string };
        detail?: { code?: string };
      };
      code = payload.error?.code ?? payload.detail?.code ?? code;
    } catch {
      // An HTTP status is enough when the response is not JSON.
    }
    throw new ApiError(response.status, code);
  }
  return response.json() as Promise<T>;
}
