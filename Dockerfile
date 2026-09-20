FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Swiss Ephemeris (расчёт натальных карт). Лицензия AGPL либо платная Professional,
# поэтому ставится только по явному флагу INSTALL_SWISSEPH=true в .env.
# Готовых сборок под Python 3.12 нет — компилируется из исходников.
ARG INSTALL_SWISSEPH=false
RUN if [ "$INSTALL_SWISSEPH" = "true" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends build-essential \
      && pip install --no-cache-dir pyswisseph==2.10.3.2 \
      && apt-get purge -y --auto-remove build-essential \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY . .

CMD ["python", "-m", "app.bot.main"]
