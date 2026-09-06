FROM --platform=${BUILDPLATFORM} node:24@sha256:8530f76a96d88820d288761f022e318970dda93d01536919fbc16076b7983e63 AS build

WORKDIR /opt/node_app

COPY . .

# do not ignore optional dependencies:
# Error: Cannot find module @rollup/rollup-linux-x64-gnu
RUN npm_config_target_arch=${TARGETARCH} yarn --frozen-lockfile --network-timeout 600000

ARG NODE_ENV=production

# Railway injects matching service variables as build args automatically.
# These are read by Vite at build time and inlined into the bundle, so a value
# missing here silently falls back to whatever .env.production ships.
ARG VITE_APP_API_URL
ARG VITE_APP_AI_BACKEND
ENV VITE_APP_API_URL=${VITE_APP_API_URL}
ENV VITE_APP_AI_BACKEND=${VITE_APP_AI_BACKEND}

RUN npm_config_target_arch=${TARGETARCH} yarn build:app:docker

FROM nginx:stable-alpine-slim@sha256:2c605dbeab79a6b2a63340474fe58119d0ef95bdc4b1f41df0aa689659b3d13b

COPY --from=build /opt/node_app/excalidraw-app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK CMD wget -q -O /dev/null http://localhost || exit 1
