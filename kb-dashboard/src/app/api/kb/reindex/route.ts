import { proxyKbRequest } from "../_shared";

export const dynamic = "force-dynamic";

export async function POST() {
  return proxyKbRequest("/api/reindex", {
    method: "POST",
  });
}