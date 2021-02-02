FROM python:3
ADD . /python-limacharlie
WORKDIR /python-limacharlie
RUN python ./setup.py install

ENTRYPOINT [ "limacharlie" ]