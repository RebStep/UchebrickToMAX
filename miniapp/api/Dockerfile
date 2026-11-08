FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --chown=node:node src ./src
RUN mkdir -p /data/files && chown node:node /data/files
ENV FILES_DIR=/data/files
USER node
CMD ["node", "src/server.js"]
