FROM python:3.12-slim AS builder

WORKDIR /build

# Install system level deps - git is needed for setuptools-scm to be able to read
# git tag (version)
RUN apt-get update && apt-get install -y git

# Install Python deps
RUN pip install --upgrade pip setuptools wheel build

COPY . ./

# Build the wheel
RUN --mount=source=.git,target=.git,type=bind \
    python -m build --wheel

FROM python:3.9-slim AS runtime

# Install package created in builder
COPY --from=builder /build/dist/limacharlie-*.whl .
RUN pip install --no-cache-dir limacharlie-*.whl

ENTRYPOINT [ "limacharlie" ]
