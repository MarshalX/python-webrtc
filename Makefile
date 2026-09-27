.PHONY: dev test lint format stub wheels doc clean

# editable install; the extension is rebuilt automatically on import after C++ changes
dev:
	uv sync --group dev --no-install-project
	uv pip install --no-build-isolation -e . \
		-Ceditable.rebuild=true -Cbuild-dir=build/editable

test:
	uv run --no-sync pytest tests $(O)

lint:
	uvx ruff check
	uvx ruff format --check

format:
	uvx ruff check --fix
	uvx ruff format

stub:
	uv run --no-sync pybind11-stubgen wrtc -o build/stubs
	cp build/stubs/wrtc.pyi stubs/wrtc/__init__.pyi

# wheels for the current platform, exactly as CI builds them
wheels:
	uvx cibuildwheel==4.2.1 --output-dir wheelhouse

doc:
	cd docs && make gen && make html

clean:
	rm -rf build dist wheelhouse
