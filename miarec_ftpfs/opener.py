# coding: utf-8
"""`FTPFS` opener definition.
"""

from __future__ import absolute_import, print_function, unicode_literals

__all__ = ["FTPOpener"]

import typing

from fs.errors import CreateFailed
from fs.opener import Opener

if typing.TYPE_CHECKING:
    from typing import Text, Union

    from miarec_ftpfs import FTPFS  # noqa: F401
    from fs.subfs import SubFS
    from fs.opener.parse import ParseResult

def asbool(val):
    if val is None:
        return False

    if isinstance(val, bool):
        return val

    if not isinstance(val, str):
        val = str(val)

    return val.lower() in ['true', '1', 't', 'y', 'yes', 'on']


class FTPOpener(Opener):
    """`FTPFS` opener."""

    protocols = ["mftp", "mftps"]

    @CreateFailed.catch_all
    def open_fs(
        self,
        fs_url,  # type: Text
        parse_result,  # type: ParseResult
        writeable,  # type: bool
        create,  # type: bool
        cwd,  # type: Text
    ):
        # type: (...) -> Union[FTPFS, SubFS[FTPFS]]
        from miarec_ftpfs import FTPFS
        from fs.subfs import ClosingSubFS

        ftp_host, _, dir_path = parse_result.resource.partition("/")
        ftp_host, _, ftp_port = ftp_host.partition(":")
        ftp_port = int(ftp_port) if ftp_port.isdigit() else 21
        ftp_fs = FTPFS(
            ftp_host,
            port=ftp_port,
            user=parse_result.username,
            passwd=parse_result.password,
            proxy=parse_result.params.get("proxy"),
            timeout=int(parse_result.params.get("timeout", "10")),
            tls=bool(parse_result.protocol == "mftps"),
            implicit_tls=asbool(parse_result.params.get("implicit_tls")),
        )
        if dir_path:
            if create:
                ftp_fs.makedirs(dir_path, recreate=True)
            return ftp_fs.opendir(dir_path, factory=ClosingSubFS)
        else:
            return ftp_fs
