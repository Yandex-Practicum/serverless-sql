FROM python:3.9-slim

ENV PGSSLROOTCERT="/secrets/.postgresql/root.crt"

# Структура папок
RUN useradd -rm -d /home/student -s /bin/bash -u 1001 student

#
RUN apt-get update && \
    apt-get install -y -q --no-install-recommends psmisc && \
	rm -rf /var/lib/apt/lists/*

# Установка агента и основных зависимостей
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    serverhub_agent==0.0.20 \
    pandas==1.2.4 \
    psutil==5.9.0 \
    -r requirements.txt && \
    rm requirements.txt && \
    chmod -R go-w /usr/local/lib/

# Добавление раннера для запуска заданий на старой либе (нужен ли?)
COPY templates/runner.py /agent/runner.py

# COPY datasets /datasets
COPY testlibs/testlib_en.py /testlibs/
COPY testlibs/sql_testlib_stable.py /testlibs/
COPY serverless-secrets/postgres_root.crt /secrets/.postgresql/root.crt


# Entrypoint
WORKDIR /agent
COPY launch.py /agent/launch.py
