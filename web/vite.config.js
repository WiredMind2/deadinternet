import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/experiments": { target: api },
      "/results": { target: api },
      "/starter": { target: api },
      "/suggest": { target: api },
      "/publications": { target: api },
      "/snapshots": { target: api },
      "/catalog": { target: api },
      "/themes": { target: api },
      "/niches": { target: api },
      "/r": { target: api },
    },
  },
});
