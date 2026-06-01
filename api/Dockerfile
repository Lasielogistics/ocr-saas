FROM python:3.11-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn httpx supabase pydantic python-jose[cryptography] passlib[bcrypt] bcrypt psycopg2-binary fpdf2

COPY main.py apm_client.py ./
COPY shared/ ./shared/
COPY invoices_api/ ./invoices_api/

RUN ln -s invoices_api api

RUN mkdir -p /chat

EXPOSE 9000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
