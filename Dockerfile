FROM python:3.11-slim

WORKDIR /srv/shopcheck

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DEFECT_MODE passes through: docker run -e DEFECT_MODE=1 ...
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
