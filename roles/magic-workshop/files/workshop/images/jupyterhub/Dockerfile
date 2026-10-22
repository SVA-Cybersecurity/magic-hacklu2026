ARG JUPYTERHUB_VERSION=5.3.0
FROM quay.io/jupyterhub/jupyterhub:${JUPYTERHUB_VERSION}

RUN python3 -m pip install --no-cache-dir \
        dockerspawner==14.0.0 \
        jupyterhub-nativeauthenticator==1.3.0 \
        bcrypt

CMD ["jupyterhub", "-f", "/srv/jupyterhub/config/jupyterhub_config.py"]
