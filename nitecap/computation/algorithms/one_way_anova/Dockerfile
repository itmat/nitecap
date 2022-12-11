FROM public.ecr.aws/lambda/python:latest
RUN pip install --no-cache-dir simplejson scipy
COPY . ./
CMD ["handler.handler"]
