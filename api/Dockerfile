FROM python:3.11-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn httpx supabase pydantic

COPY main.py apm_client.py ./

RUN mkdir -p /chat

EXPOSE 9000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
