# syntax=docker/dockerfile:1

# Astro 5.x engine requires Node 18.20.8 / 20.3.0 / >=22
ARG NODE_VERSION=22
ARG DEBIAN_VERSION=bullseye
ARG DOCKER_LIBRARY_REGISTRY=docker.io/library

FROM ${DOCKER_LIBRARY_REGISTRY}/node:${NODE_VERSION}-${DEBIAN_VERSION} AS build

WORKDIR /app
COPY package.json package-lock.json ./

RUN npm ci

COPY . .
ENV NODE_ENV=production
RUN npm run build
RUN npm prune --omit=dev

FROM ${DOCKER_LIBRARY_REGISTRY}/node:${NODE_VERSION}-${DEBIAN_VERSION} AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist

EXPOSE 3000
CMD ["npx", "astro", "preview", "--host", "0.0.0.0", "--port", "3000"]

