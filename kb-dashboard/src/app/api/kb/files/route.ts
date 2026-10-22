import { proxyKbRequest } from "../_shared";

export const dynamic = "force-dynamic";

export async function GET() {
  return proxyKbRequest("/api/files", { method: "GET" });
}