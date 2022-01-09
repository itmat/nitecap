FROM mcr.microsoft.com/vscode/devcontainers/base:hirsute

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update                                                                                                                      \
 && apt-get install -y apache2-dev black pip                                                                                            \
 && apt-get install -y libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libgconf-2-4 libnss3 libxss1 libasound2 libxtst6 xauth xvfb

RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"                                                   \
 && unzip awscliv2.zip                                                                                                                  \
 && ./aws/install                                                                                                                       \
 && rm -rf awscliv2.zip aws

COPY src/server/requirements.txt .

RUN pip install -r requirements.txt

COPY .devcontainer/setup.sh /home/vscode/
