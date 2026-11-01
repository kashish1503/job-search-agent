# Stage 1: frontend builder
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend
COPY src/frontend/package.json src/frontend/package-lock.json* ./
RUN npm install
COPY src/frontend/ ./
RUN npm run build

# Stage 2: final image
FROM python:3.12-slim

WORKDIR /app

# Install system deps: texlive for PDF compilation, plus Playwright system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    latexmk \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

# Copy application source
COPY src/ ./src/

# Copy built frontend assets from stage 1
COPY --from=frontend-builder /build/frontend/dist ./src/frontend/dist

# Ensure data directories exist
RUN mkdir -p /app/data /app/data/resumes

CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
