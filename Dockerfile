FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt && python init_render.py

COPY . .

CMD ["python", "main_with_payments.py"]
