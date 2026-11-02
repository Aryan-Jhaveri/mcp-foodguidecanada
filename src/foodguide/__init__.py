"""foodguide: Canada's Food Guide data tools."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("foodguide")
except PackageNotFoundError:  # not installed (e.g. running from a raw checkout)
    __version__ = "0.1.0"
