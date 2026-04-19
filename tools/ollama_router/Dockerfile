FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8080
# Mac + socat to lab Ollama: use 11435 on host (see tools/ollama_router run example).
ENV OLLAMA_UPSTREAM=http://host.docker.internal:11435
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
