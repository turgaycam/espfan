"""Geliştirme ortamı duman testi: VM venv'inde Python 3.12 + pytest 8."""
import sys

import pytest


def test_python_surumu():
    assert sys.version_info[:2] == (3, 12)


def test_venv_icinde_calisiyor():
    assert sys.prefix != sys.base_prefix
    assert pytest.__version__.startswith("8.")
