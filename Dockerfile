FROM python:slim
ADD . /python-limacharlie
WORKDIR /python-limacharlie
RUN python ./setup.py install

ENTRYPOINT [ "limacharlie" ]