FROM public.ecr.aws/lambda/python:latest
RUN pip install -U pip && pip install simplejson scipy
COPY . ./
CMD ["handler.handler"]
