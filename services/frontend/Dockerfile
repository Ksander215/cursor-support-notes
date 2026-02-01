# syntax=docker/dockerfile:1

# Astro 5.x engine requires Node 18.20.8 / 20.3.0 / >=22
# Use fixed image name so .env.production cannot break FROM (e.g. merged lines).
FROM docker.io/library/node:22-bullseye AS build

WORKDIR /app
COPY package.json package-lock.json ./

RUN npm ci

COPY . .
ENV NODE_ENV=production
RUN npm run build
RUN npm prune --omit=dev

FROM docker.io/library/node:22-bullseye AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist

EXPOSE 3000
CMD ["npx", "astro", "preview", "--host", "0.0.0.0", "--port", "3000"]
