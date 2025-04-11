FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080

CMD streamlit run --server.port 8080 --server.enableCORS false --server.enableXsrfProtection false analyse_csv_xml_v3.py
