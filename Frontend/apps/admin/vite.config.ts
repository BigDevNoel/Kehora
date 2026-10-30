import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: "../../..",
  server: { port: 5174, strictPort: true, host: true },
  preview: { port: 5174, strictPort: true, host: true },
});
