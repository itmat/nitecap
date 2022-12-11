FROM public.ecr.aws/lambda/python:latest
RUN pip install --no-cache-dir simplejson statsmodels
COPY . ./
CMD ["handler.handler"]
