import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { User } from "./types";

export async function requireUser(): Promise<User> {
  const token = (await cookies()).get("ava_session");
  if (!token) redirect("/login");

  const backend = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  const response = await fetch(`${backend}/api/me`, {
    headers: { Cookie: `ava_session=${token.value}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/login");
  if (!response.ok) throw new Error("Ava backend is unavailable.");
  return response.json() as Promise<User>;
}
