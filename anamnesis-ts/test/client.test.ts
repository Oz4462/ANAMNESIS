import { describe, expect, it } from "vitest";

import { AnamnesisClient } from "../src/client.js";

function mockFetchOnce(response: { status: number; body: unknown }): typeof fetch {
  const fn = async (_input: RequestInfo | URL, init?: RequestInit) => {
    return {
      ok: response.status >= 200 && response.status < 300,
      status: response.status,
      statusText: "OK",
      text: async () => JSON.stringify(response.body),
      json: async () => response.body,
    } as Response;
  };
  return fn as unknown as typeof fetch;
}

describe("AnamnesisClient", () => {
  it("health returns parsed body", async () => {
    const client = new AnamnesisClient({
      baseUrl: "https://example.invalid",
      fetchFn: mockFetchOnce({ status: 200, body: { status: "ok", version: "0.2.0" } }),
    });
    const out = await client.health();
    expect(out.status).toBe("ok");
  });

  it("calibrationStatus URL-encodes tenant", async () => {
    let capturedUrl = "";
    const client = new AnamnesisClient({
      baseUrl: "https://example.invalid",
      fetchFn: async (url) => {
        capturedUrl = String(url);
        return {
          ok: true,
          status: 200,
          statusText: "OK",
          text: async () =>
            JSON.stringify({ tenant_id: "x", n_calibration: 0, ready: false, alpha: 0.1 }),
        } as Response;
      },
    });
    await client.calibrationStatus("tenant with spaces");
    expect(capturedUrl).toContain("/v1/calibration/tenant%20with%20spaces");
  });

  it("throws on non-2xx", async () => {
    const client = new AnamnesisClient({
      baseUrl: "https://example.invalid",
      fetchFn: mockFetchOnce({ status: 500, body: { detail: "boom" } }),
    });
    await expect(client.health()).rejects.toThrow(/HTTP 500/);
  });
});
