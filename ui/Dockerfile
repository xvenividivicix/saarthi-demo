FROM node:18-slim
WORKDIR /app
COPY . .
RUN npm i -g serve
EXPOSE 5173
CMD ["serve", "-s", ".", "-l", "5173"]
