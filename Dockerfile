FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Asia/Riyadh ABELLA_HOSTED=1 DATA_DIR=/data
WORKDIR /app
RUN pip install --no-cache-dir openpyxl cryptography
COPY . .
CMD ["python", "start.py"]
