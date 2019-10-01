FROM python:3.6-stretch

ENV DEBIAN_FRONTEND noninteractive


#RUN apt install dirmngr \
#&& apt-key adv --keyserver keys.gnupg.net --recv-key 'E19F5F87128899B192B1A2C2AD5F960A256A04AF'


#RUN apt-get update \
#&& apt-get install -y software-properties-common \
#&& apt-get install -y apt-transport-https ca-certificates

#RUN add-apt-repository 'deb https://cloud.r-project.org/bin/linux/debian stretch-cran35/'

RUN apt-get update \
&& apt-get install -y apt-utils \
&& apt-get install -y libmagic-dev \
&& apt-get install -y apache2 \
&& apt-get install -y apache2-dev \
&& apt-get install -y r-base \
&& apt-get install -y sqlite3 \
&& mkdir -p /var/www/flask_apps/nitecap

WORKDIR /var/www/flask_apps/nitecap

RUN Rscript -e 'install.packages(c("readr", "stringr"), repos="http://cran.r-project.org")'

ADD requirements.txt .

RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python3","app.py"]
