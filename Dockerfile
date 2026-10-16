FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY model_quality_lab ./model_quality_lab
COPY configs ./configs
COPY docs ./docs
RUN pip install --no-cache-dir '.[kafka]' && mkdir -p /app/.runtime
ENV MQL_RUNTIME=/app/.runtime
EXPOSE 7856
CMD ["uvicorn","model_quality_lab.service:app","--host","0.0.0.0","--port","7856"]
