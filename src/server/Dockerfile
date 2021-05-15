FROM python:3.6-buster

ENV DEBIAN_FRONTEND noninteractive

# Change the GID from 33 to 1001 so that it doesn't conflict with the group tape on the host OS
RUN groupmod -g 1001 www-data \
  && usermod -u 1001 -g 1001 www-data \
  && apt-get update \
  && apt-get install -y apt-utils \
  && apt-get install -y libmagic-dev \
  && apt-get install -y apache2 \
  && apt-get install -y apache2-dev \
  && apt-get install -y sqlite3 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir -p /var/www/flask_apps/nitecap \
  && pip install --upgrade pip

# Install the python packages we use
ADD requirements.txt .
RUN pip --no-cache-dir install -r requirements.txt
RUN mkdir /var/www/flask_apps/logs

WORKDIR /var/www/flask_apps/nitecap
COPY --chown=www-data . .
COPY --chown=www-data .env_example .env

# Prepare apache
COPY apache/nitecap.conf /etc/apache2/sites-available/
RUN a2dissite 000-default.conf \
 && a2ensite nitecap.conf \
 && mod_wsgi-express module-config >> /etc/apache2/apache2.conf \
 && echo "Listen 5000" >> /etc/apache2/ports.conf

CMD ["/bin/bash", "start_server.sh"]

