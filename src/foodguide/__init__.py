"""foodguide: Canada's Food Guide data tools."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("foodguidecanada")
except PackageNotFoundError:  # not installed (e.g. running from a raw checkout)
    __version__ = "3.0.0"
