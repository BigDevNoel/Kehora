# Studio, admin and site dev servers. Context: ./Frontend
# node_modules are built in the image (Linux binaries); for hot reload run `pnpm dev` on the host.
FROM node:24-slim

RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /app
COPY . .
RUN pnpm install --frozen-lockfile
ENV HOST=0.0.0.0
CMD ["pnpm", "--filter", "@kehora/studio", "dev"]
