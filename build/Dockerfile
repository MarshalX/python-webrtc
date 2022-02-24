ARG MANYLINUX_ARCH
# self pathed cpython https://github.com/MarshalX/manylinux-cpython-pathes
FROM quay.io/pypa_patched/manylinux_2_24_$MANYLINUX_ARCH AS builder

RUN apt-get update && apt-get install -y xz-utils libxml2 wget build-essential

WORKDIR /opt
RUN wget http://ftp.mirrorservice.org/sites/sourceware.org/pub/gcc/releases/gcc-7.5.0/gcc-7.5.0.tar.gz && \
    tar zxf gcc-7.5.0.tar.gz
WORKDIR gcc-7.5.0
RUN ./contrib/download_prerequisites && \
    ./configure --disable-multilib && \
    make -j $(nproc) && \
    make install && \
    make clean
