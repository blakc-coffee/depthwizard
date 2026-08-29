/** Supabase client. Auth only — the frontend never touches Postgres or Storage
 *  directly; artifacts arrive as signed URLs from the backend (PRD §10.1). */

import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  console.warn("Supabase env vars missing — see .env.example");
}

export const supabase = createClient(url ?? "", anonKey ?? "", {
  auth: { persistSession: true, autoRefreshToken: true },
});
