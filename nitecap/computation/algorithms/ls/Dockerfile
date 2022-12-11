FROM public.ecr.aws/lambda/python:latest
RUN pip install --no-cache-dir simplejson numpy
COPY . ./
CMD ["handler.handler"]
