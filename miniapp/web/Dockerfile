FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# только сборка: проверку типов (vue-tsc) уже сделал GitHub в задании build, а на сервере она
# долгая и забирает много памяти, которую держат модели распознавания голоса
RUN npx vite build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
