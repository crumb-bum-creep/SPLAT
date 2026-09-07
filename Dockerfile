FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/SPLAT
COPY . /workspace/SPLAT
RUN bash /workspace/SPLAT/install.sh

EXPOSE 7860
CMD ["bash", "/workspace/SPLAT/serve.sh"]
