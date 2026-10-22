ARG SINGLEUSER_BASE_IMAGE=quay.io/jupyter/base-notebook:python-3.11
FROM ${SINGLEUSER_BASE_IMAGE}

ARG JUPYTERHUB_VERSION=5.3.0
ARG MAGIC_REF=main

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER ${NB_UID}

RUN pip install --no-cache-dir \
        "jupyterhub==${JUPYTERHUB_VERSION}" \
        "git+https://github.com/SVA-Cybersecurity/magic.git@${MAGIC_REF}" \
        timesketch-api-client \
        timesketch-import-client \
        pandas \
        matplotlib \
        tabulate \
    && fix-permissions "${CONDA_DIR}" \
    && fix-permissions "/home/${NB_USER}"

WORKDIR /home/jovyan/work
