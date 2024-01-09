from __future__ import absolute_import
from __future__ import unicode_literals

__all__ = ["FTPFS"]

from .ftpfs import FTPFS

__license__ = "MIT"
__copyright__ = "Copyright (c) MiaRec"
__author__ = "MiaRec <support@miarec.com>"
__version__ = (
    __import__("pkg_resources")
    .resource_string(__name__, "_version.txt")
    .strip()
    .decode("ascii")
)

