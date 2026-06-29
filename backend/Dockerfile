FROM python:3.10-slim

WORKDIR /app

# System deps for gitpython and tree-sitter compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Workspace dir for cloned repos / uploads
RUN mkdir -p /app/workspace

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
