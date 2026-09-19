# fuw.lol web — the SvelteKit build served by nginx, which also proxies the API and serves
# uploaded files straight from the shared media volume.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# --ignore-scripts, and the `npm run prepare` further down, are one fix with two halves.
# This project's `prepare` script runs scripts/scope-latexjs-css.mjs, which READS
# node_modules/latex.js/dist/css and WRITES src/lib/render/latexjs.scoped.css — and at
# this line the source tree is not here yet, only the two manifests, so it died with
# ENOENT and took `npm ci` down with it. Copying the whole tree first would fix it and
# throw away the dependency layer cache on every source change; this keeps the cache and
# moves the lifecycle script to where its inputs exist.
RUN npm ci --no-audit --no-fund --ignore-scripts
COPY . .
RUN npm run prepare
ENV PUBLIC_API_BASE_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
# The base image ships /usr/share/nginx/html/{index,50x}.html, and COPY MERGES into that
# directory rather than replacing it. This app is a pure SPA whose entry point is
# 200.html (vite.config.ts), so it has no index.html of its own to overwrite nginx's —
# and `try_files $uri $uri/ /200.html` resolves `/` to the directory, where the `index`
# directive then finds nginx's leftover welcome page. The homepage was "Welcome to
# nginx!". Clearing the directory first is the whole fix.
RUN rm -rf /usr/share/nginx/html/*
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
