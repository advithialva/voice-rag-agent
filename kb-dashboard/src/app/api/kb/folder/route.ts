import { proxyKbRequest } from "../_shared";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.text();
  return proxyKbRequest("/api/folder", {
    method: "POST",
    body,
  });
}
