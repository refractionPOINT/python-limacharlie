FROM python:3.12-slim
ADD . /python-limacharlie
WORKDIR /python-limacharlie
RUN pip install .
ENTRYPOINT [ "limacharlie" ]
