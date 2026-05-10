FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
RUN python init_render.py
CMD ["python", "main_with_payments.py"]
