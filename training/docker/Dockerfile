# FinQuant QLoRA / verifier eval — GPU training image.
#
# Build (repository root = context):
#   docker build -f training/docker/Dockerfile -t blackbox-finquant-train:rtx40 .
#
# Requires: NVIDIA Container Toolkit on the host (`docker run --gpus all`).
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BITSANDBYTES_NOWELCOME=1

WORKDIR /workspace

COPY training/requirements-finquant-training-docker.txt /tmp/requirements-extras.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements-extras.txt \
    && rm -f /tmp/requirements-extras.txt

# Mount blackbox at /workspace/blackbox and FINQUANT_BASE at runtime.
WORKDIR /workspace/blackbox
CMD ["bash", "-lc", "echo 'FinQuant train image ready. Run training/docker/run_smoke.sh from the host.' && bash"]
