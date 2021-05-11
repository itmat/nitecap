FROM python:3.6-stretch

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update \
  && apt-get install -y apt-utils \
  && apt-get install -y libmagic-dev \
  && apt-get install -y apache2 \
  && apt-get install -y apache2-dev \
  && apt-get install -y sqlite3 \
  && mkdir -p /var/www/flask_apps/nitecap \
  && pip install --upgrade pip



# Install the python packages we use
ADD requirements.txt .
RUN pip --no-cache-dir install -r requirements.txt

RUN mkdir /nitecap_web \
  && mkdir /nitecap_web/uploads \
  && mkdir /nitecap_web/db_backup \
  && mkdir /nitecap_web/db \
  && touch /nitecap_web/log \
  && chown -R www-data /nitecap_web
RUN mkdir /var/www/flask_apps/logs

WORKDIR /var/www/flask_apps/nitecap
COPY --chown=www-data . .

# Prepare apache
COPY apache/nitecap.conf /etc/apache2/sites-available/
RUN a2dissite 000-default.conf \
 && a2ensite nitecap.conf \
 && mod_wsgi-express module-config >> /etc/apache2/apache2.conf \
 && echo "Listen 5000" >> /etc/apache2/ports.conf

EXPOSE 80

CMD ["sh", "start_server.sh"]
#CMD ["/usr/sbin/apache2ctl","-DFOREGROUND"]