import node from "@astrojs/node";
import { defineConfig } from "astro/config";

// Server-rendered public site and (later) marketplace listings; see CLAUDE.md stack.
export default defineConfig({
  output: "server",
  adapter: node({ mode: "standalone" }),
  server: { host: true, port: 4321 },
  vite: { envDir: "../../.." },
});
