FROM python:3.6-jessie

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update \
&& apt-get install -y apt-utils \
&& apt-get install -y libmagic-dev \
&& apt-get install -y apache2 \
&& apt-get install -y apache2-dev \
&& sh /etc/apache2/envvars \
&& mkdir -p /var/www/flask_apps/nitecap

WORKDIR /var/www/flask_apps/nitecap

ADD requirements.txt .

RUN pip install --upgrade setuptools && pip install -r requirements.txt

COPY . .

EXPOSE 5000

VOLUME /Users/crislawrence/Documents/Work/nitecap.db

CMD ["python3","app.py"]