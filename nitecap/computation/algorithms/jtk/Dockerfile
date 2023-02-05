FROM public.ecr.aws/lambda/python:latest

ARG R=4.2.2

RUN yum install -y bzip2-devel curl-devel gcc gcc-c++ gcc-gfortran gzip make pcre2-devel perl tar wget which xz-devel zlib-devel \
 && wget -q -O - https://cran.r-project.org/src/base/R-$(echo $R | cut -c 1)/R-$R.tar.gz | tar xzf -                             \
 && cd R-$R                                                                                                                      \
 && ./configure --enable-R-shlib --disable-openmp --disable-R-profiling --disable-java --disable-nls                             \
    --without-ICO --without-readline --without-recommended-packages --without-tcltk --without-x                                  \
    --without-cairo --without-jpeglib --without-libpng --without-libtiff                                                         \
 && make -j $(nproc)                                                                                                             \
 && make install                                                                                                                 \
 && rm -rf ../R-$R                                                                                                               \
 && yum remove -y bzip2-devel curl-devel gcc gcc-c++ gcc-gfortran gzip pcre2-devel perl tar wget xz-devel zlib-devel             \
 && yum clean all -y && rm -rf /var/cache

RUN ln -s /usr/local/lib64/R/lib /usr/local/lib64/R/lib64
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib64/R/lib64

RUN pip install --no-cache-dir rpy2 simplejson numpy

COPY . ./

CMD ["handler.handler"]
