# fuw.lol web — the SvelteKit build served by nginx, which also proxies the API and serves
# uploaded files straight from the shared media volume.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ENV PUBLIC_API_BASE_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
