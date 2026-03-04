"""
Entry point for running orbitclaw as a module: python -m orbitclaw
"""

from orbitclaw.app.cli.commands import app

if __name__ == "__main__":
    app()
