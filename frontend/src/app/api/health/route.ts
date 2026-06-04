import { NextResponse } from "next/server";

export async function GET() {
  try {
    // Attempt to fetch from FastAPI backend health endpoint
    const backendUrl = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    const res = await fetch(`${backendUrl}/api/v1/health`, {
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`FastAPI backend responded with status: ${res.status}`);
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error: any) {
    // If backend is unreachable or throws an error, catch and return structured payload
    return NextResponse.json(
      {
        status: "unreachable",
        database: "disconnected",
        api_version: "v1",
        error: error.message || "Failed to reach FastAPI backend",
      }
    );
  }
}
