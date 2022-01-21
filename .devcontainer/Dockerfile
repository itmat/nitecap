FROM mcr.microsoft.com/vscode/devcontainers/base:hirsute

RUN apt-get update                                                                              \
 && apt-get install -y apache2-dev black pip

RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"           \
 && unzip awscliv2.zip                                                                          \
 && ./aws/install                                                                               \
 && rm -rf awscliv2.zip aws

COPY src/server/requirements.txt .

RUN pip install -r requirements.txt

COPY .devcontainer/setup.sh /home/vscode/

