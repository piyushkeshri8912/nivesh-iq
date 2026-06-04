import { createNeonAuth } from '@neondatabase/auth/next/server';

if (!process.env.NEON_AUTH_BASE_URL || !process.env.NEON_AUTH_COOKIE_SECRET) {
  console.error("ERROR: Missing NEON_AUTH_BASE_URL or NEON_AUTH_COOKIE_SECRET in frontend environment.");
}

export const auth = createNeonAuth({
  baseUrl: process.env.NEON_AUTH_BASE_URL || "http://localhost:3000/api/auth",
  cookies: { 
    secret: process.env.NEON_AUTH_COOKIE_SECRET || "fallback-dev-secret-do-not-use-in-production" 
  }
});

export const { GET, POST } = auth.handler();
