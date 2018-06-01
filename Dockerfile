FROM python:2.7
ADD . /python-limacharlie
WORKDIR /python-limacharlie
RUN python ./setup.py install