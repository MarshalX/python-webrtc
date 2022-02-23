# TODO (MarshalX) make it more pretty
PATH_TO_WRTC_SO = ../../build/lib.macosx-12.1-arm64-3.10/wrtc.cpython-310-darwin.so
PATH_TO_PY_MODULES = ./python-webrtc/python

RUN_TESTS = pytest
RUN_TESTS_OPTS ?= -W ignore:::wrtc -W ignore:::pkg_resources
TESTS_DIR = tests

export PATH_TO_LIB=${PATH_TO_WRTC_SO}
export PYTHONPATH=${PATH_TO_PY_MODULES}

test:
	@${RUN_TESTS} ${TESTS_DIR} ${RUN_TESTS_OPTS} $(O)
