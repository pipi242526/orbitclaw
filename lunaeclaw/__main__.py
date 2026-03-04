"""
Entry point for running lunaeclaw as a module: python -m lunaeclaw
"""

from lunaeclaw.app.cli.commands import app

if __name__ == "__main__":
    app()
