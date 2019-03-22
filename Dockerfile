FROM python:3.6-jessie

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update \
&& apt-get install -y apt-utils \
&& apt-get install -y libmagic-dev \
&& apt-get install -y apache2 \
&& apt-get install -y apache2-dev \
&& apt-get install -y R-base \
&& mkdir -p /var/www/flask_apps/nitecap

WORKDIR /var/www/flask_apps/nitecap

ADD requirements.txt .

RUN pip install -r requirements.txt
RUN Rscript -e 'install.packages("readr", repos="http://cran.r-project.org")'

COPY . .

EXPOSE 5000

CMD ["python3","app.py"]
