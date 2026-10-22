import { NextResponse } from "next/server";

type JsonRecord = Record<string, unknown>;

const kbAdminBaseUrl =
  process.env.KB_ADMIN_API_BASE_URL?.replace(/\/+$/, "") ?? "http://127.0.0.1:8090";

function messageFromPayload(payload: JsonRecord | null): string {
  if (!payload) {
    return "KB admin request failed.";
  }

  const detail = payload.detail;
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }

  const message = payload.message;
  if (typeof message === "string" && message.length > 0) {
    return message;
  }

  return "KB admin request failed.";
}

export async function proxyKbRequest(path: string, init?: RequestInit): Promise<NextResponse> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(`${kbAdminBaseUrl}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });

    const contentType = response.headers.get("content-type") ?? "";
    let payload: JsonRecord | null = null;

    if (contentType.includes("application/json")) {
      payload = (await response.json()) as JsonRecord;
    } else {
      const textPayload = await response.text();
      payload = textPayload ? { message: textPayload } : {};
    }

    if (!response.ok) {
      return NextResponse.json(
        {
          ok: false,
          message: messageFromPayload(payload),
        },
        { status: response.status },
      );
    }

    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    const reason = error instanceof Error ? error.message : "Unknown network error.";
    return NextResponse.json(
      {
        ok: false,
        message: `Cannot connect to KB admin backend at ${kbAdminBaseUrl}. ${reason}`,
      },
      { status: 503 },
    );
  }
}