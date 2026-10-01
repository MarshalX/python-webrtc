.PHONY: dev test asan tsan fuzz lint typecheck format format-check tidy stub wheels doc clean

# pinned to the clang-tidy of .github/scripts/tidy.sh
CLANG_FORMAT := uvx clang-format==22.1.8
CPP_SRC = $(shell find python-webrtc/cpp/src -name '*.cpp' -o -name '*.h')

# editable install; the extension is rebuilt automatically on import after C++ changes
dev:
	uv sync --group dev --no-install-project
	uv pip install --no-build-isolation -e . \
		-Ceditable.rebuild=true -Cbuild-dir=build/editable

test:
	uv run --no-sync pytest tests $(O)

# the tests against an ASan+UBSan build, natively on macOS (on Linux: .github/scripts/sanitizers.sh)
asan:
	.github/scripts/sanitizers-macos.sh $(O)

tsan:
	SANITIZE=thread .github/scripts/sanitizers-macos.sh $(O)

# a target of tests/fuzz with Atheris in the Linux image, the build kept in build/fuzz: make fuzz T=video_frame O=-max_total_time=600
fuzz:
	docker run --rm -it --platform linux/amd64 -v "$(CURDIR):/src" -v "$(CURDIR)/build/fuzz:/tmp/wrtc-fuzz" \
		-e WRTC_CACHE_DIR=/tmp/wrtc-fuzz/cache -w /src \
		quay.io/pypa/manylinux_2_28_x86_64 .github/scripts/fuzz.sh $(T) $(O)

lint: format-check
	uvx ruff check
	uvx ruff format --check

typecheck:
	uvx pyrefly check

format:
	uvx ruff check --fix
	uvx ruff format
	$(CLANG_FORMAT) -i $(CPP_SRC)

format-check:
	@$(CLANG_FORMAT) --dry-run --Werror $(CPP_SRC)

# clang-tidy over the extension, see .clang-tidy
tidy:
	.github/scripts/tidy.sh $(O)

stub:
	uv run --no-sync pybind11-stubgen wrtc -o build/stubs
	cp build/stubs/wrtc.pyi stubs/wrtc/__init__.pyi
	# collections.abc.Buffer is 3.12+
	perl -pi -e 's/collections\.abc\.Buffer/typing_extensions.Buffer/g; s/^import typing$$/import typing\nimport typing_extensions/' stubs/wrtc/__init__.pyi

# wheels for the current platform, exactly as CI builds them
wheels:
	uvx cibuildwheel==4.2.1 --output-dir wheelhouse

doc:
	cd docs && make gen && make html

clean:
	rm -rf build dist wheelhouse
