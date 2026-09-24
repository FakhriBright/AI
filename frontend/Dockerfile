FROM node:20-alpine

WORKDIR /app

# Copy package requirements first for caching layer
COPY package*.json ./

RUN npm ci || npm install

# Copy application source code
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
