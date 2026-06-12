# Build from the parent xapp directory:
# docker build --network=host -f basic-xapp/Dockerfile -t registry.local:5000/steering-wheel-command-xapp:1.0.0 .

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_FILE=/opt/ric/config/config-file.json \
    RMR_RTG_SVC=9999 \
    RMR_SEED_RT=/opt/xapp/routes.txt

WORKDIR /opt/xapp

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    musl \
    gcc \
    build-essential \
    python3-dev \
    && wget -nv --content-disposition https://packagecloud.io/o-ran-sc/release/packages/debian/stretch/rmr_4.9.4_amd64.deb/download.deb \
    && dpkg -i rmr_4.9.4_amd64.deb \
    && rm -f rmr_4.9.4_amd64.deb \
    && if [ -e /usr/lib/x86_64-linux-musl/libc.so ]; then ln -sf /usr/lib/x86_64-linux-musl/libc.so /lib/libc.musl-x86_64.so.1; fi \
    && mkdir -p /opt/ric/config \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir ricxappframe pygame numpy \
    && apt-get purge -y --auto-remove wget \
    && rm -rf /var/lib/apt/lists/*

COPY basic-xapp/steering_xapp.py /opt/xapp/
COPY basic-xapp/steering_service.py /opt/xapp/
COPY basic-xapp/wheel_client.py /opt/xapp/
COPY basic-xapp/forwarder_helper.py /opt/xapp/
COPY basic-xapp/xapp-descriptor.json /opt/xapp/
COPY basic-xapp/routes.txt /opt/xapp/
COPY basic-xapp/README.md /opt/xapp/

# Keep a fallback copy in the image.
# Kubernetes/Helm may still override /opt/ric/config with a mounted ConfigMap.
COPY basic-xapp/config.json /opt/ric/config/config-file.json

EXPOSE 8080 4562

CMD ["python3", "/opt/xapp/steering_xapp.py"]
