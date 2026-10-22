import { NextResponse } from "next/server";

import { proxyKbRequest } from "../_shared";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");

  if (!path) {
    return NextResponse.json(
      {
        ok: false,
        message: "Missing required query parameter: path",
      },
      { status: 400 },
    );
  }

  return proxyKbRequest(`/api/file?path=${encodeURIComponent(path)}`, { method: "GET" });
}

export async function DELETE(request: Request) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");

  if (!path) {
    return NextResponse.json(
      {
        ok: false,
        message: "Missing required query parameter: path",
      },
      { status: 400 },
    );
  }

  return proxyKbRequest(`/api/file?path=${encodeURIComponent(path)}`, { method: "DELETE" });
}