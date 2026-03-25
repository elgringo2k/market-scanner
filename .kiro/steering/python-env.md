# Python Environment

This project uses a `.venv` virtual environment at the project root.

When running any Python, pip, or pytest commands, always use the venv binaries directly:

- Python: `.venv/bin/python`
- Pytest: `.venv/bin/pytest`
- Pip: `.venv/bin/pip`

Never use bare `python`, `python3`, `pip`, or `pytest` commands — always prefix with `.venv/bin/`.

To activate manually: `source .venv/bin/activate`
