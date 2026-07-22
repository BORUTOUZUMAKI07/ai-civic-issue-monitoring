FROM quay.io/astronomer/astro-runtime:12.7.0

USER root
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

USER airflow

COPY --chown=airflow:airflow packages.txt /tmp/packages.txt
RUN if [ -s /tmp/packages.txt ]; then apt-get update && xargs -a /tmp/packages.txt apt-get install -y --no-install-recommends && rm -rf /var/lib/apt/lists/*; fi

COPY --chown=airflow:airflow requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=airflow:airflow include/ /usr/local/airflow/include/
COPY --chown=airflow:airflow plugins/ /usr/local/airflow/plugins/
