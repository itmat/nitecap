FROM public.ecr.aws/lambda/python:latest
RUN pip install -U pip && pip install simplejson numpy
COPY . ./
CMD ["handler.handler"]
