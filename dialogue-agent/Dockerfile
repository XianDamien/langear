FROM node:24-alpine
RUN npm install --global pnpm@10.14.0
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY --chown=node:node src ./src
CMD ["pnpm", "start"]
