FROM mcr.microsoft.com/vscode/devcontainers/base:hirsute

ENV R=R-4.2.0

ENV JOBS=8

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update                                                                                                                  \
 && apt-get install -y apache2-dev black gfortran pip                                                                               \
 && apt-get install -y libbz2-dev libcurl4-openssl-dev libgmp-dev liblzma-dev libpcre2-dev libreadline-dev libxt-dev

# For end-to-end testing
RUN apt-get install -y libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libgconf-2-4 libnss3 libxss1 libasound2 libxtst6 xauth xvfb

RUN wget -q -O - https://cran.r-project.org/src/base/$(echo $R | cut -c 1-3)/$R.tar.gz | tar xzf -                                  \
 && cd $R                                                                                                                           \
 && ./configure --enable-R-shlib --disable-prebuilt-html --without-x                                                                \
 && make -j $JOBS                                                                                                                   \
 && make install                                                                                                                    \
 && rm -rf /$R

ENV R_HOME=/usr/local/lib/R

RUN echo "options(repos=c(CRAN='https://cloud.r-project.org'), Ncpus=$JOBS)" >> $R_HOME/etc/Rprofile.site

RUN R -e "install.packages(c('BiocManager', 'MetaCycle'))"
RUN R -e "BiocManager::install('rain')"

RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"                                               \
 && unzip awscliv2.zip                                                                                                              \
 && ./aws/install                                                                                                                   \
 && rm -rf awscliv2.zip aws

COPY src/server/requirements.txt .

RUN pip install -r requirements.txt                                                                                                 \
 && pip install ipykernel statsmodels rpy2

ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/R/lib/

COPY .devcontainer/setup.sh /home/vscode/
