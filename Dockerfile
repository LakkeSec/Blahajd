# Blahajd — the yearly role refresh bot
#
# Build:
#   docker build -t blahajd .
#
# Run (with a filled-in .env from the setup steps in the README):
#   docker run -d --name blahajd --env-file .env \
#     -v blahajd-data:/data --restart unless-stopped blahajd
#
# Set DB_PATH=/data/blahajd.db in your .env so the database lives on the
# volume and survives container rebuilds.

FROM python:3.12-slim

# unbuffered stdout so `docker logs` shows the bot's logs in real time;
# no .pyc writes since the app user can't write to /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/data/blahajd.db

WORKDIR /app

# run as an unprivileged user; a fresh named volume mounted at /data
# inherits this directory's ownership, so the bot can write the sqlite db
RUN useradd --create-home --uid 1000 blahajd \
    && mkdir -p /data && chown blahajd:blahajd /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

USER blahajd

CMD ["python", "bot.py"]
