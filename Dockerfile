FROM python:3.12-slim
ADD . /python-limacharlie
WORKDIR /python-limacharlie
RUN python -m pip install "setuptools==75.8.0"
RUN python ./setup.py install

ENTRYPOINT [ "limacharlie" ]
