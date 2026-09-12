FROM ghcr.io/blakeblackshear/frigate:0.17.2

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-tools \
    && rm -rf /var/lib/apt/lists/*
