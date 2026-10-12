FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/app.py
RUN useradd --uid 10001 --create-home appuser
USER 10001
EXPOSE 8080
ENV PYTHONUNBUFFERED=1
CMD ["python", "app.py"]
