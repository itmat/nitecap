FROM public.ecr.aws/lambda/python:latest

ENV R_VERSION=4.0.5
RUN yum -y install bzip2-devel curl-devel gcc gcc-c++ gcc-gfortran gzip make pcre2-devel tar wget which xz-devel zlib-devel \
  && wget http://cran.rstudio.com/src/base/R-4/R-${R_VERSION}.tar.gz \
  && tar xvf R-${R_VERSION}.tar.gz \
  && rm R-${R_VERSION}.tar.gz \
  && mv R-${R_VERSION} /opt/R \
  && cd /opt/R \
  && ./configure --enable-R-shlib --enable-R-profiling=no \
    --with-ICU=no --enable-java=no --disable-nls --with-readline=no --with-tcltk=no --with-x=no \
    --with-cairo=no --with-jpeglib=no --with-libpng=no --with-libtiff=no \
    --with-recommended-packages=no \
  && make \
  && rm -r src \
  && yum -y remove bzip2-devel curl-devel gcc gcc-c++ gcc-gfortran gzip make pcre2-devel tar wget xz-devel zlib-devel \
  && yum clean all
ENV PATH="${PATH}:/opt/R/bin/"
ENV LD_LIBRARY_PATH="/opt/R/lib/"

RUN pip install -U pip && pip install rpy2 simplejson statsmodels
COPY . ./
CMD ["handler.handler"]
