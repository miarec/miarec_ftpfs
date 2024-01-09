# miarec_s3fs

MiaRec FTPFS is a [PyFilesystem](https://www.pyfilesystem.org/) interface to
FTP/FTPS storage.

This a fork of the builtin FTPFS class from [PyFileSystem2](https://github.com/PyFilesystem/pyfilesystem2) project, written by Will McGugan (email willmcgugan@gmail.com). 

The code was modified by MiaRec team to fullfill our needs.

## Notable differences between miarec_s3fs and fs-s3fs

1. Requires Python 3.6+. A support of Python 2.7 is removed.

2. Opener is not implemented. Use an explicit constructor instead.

## Installing

You can install FTPFS from pip as follows:

```
pip install miarec_ftpfs
```

This will install the most recent stable version.

Alternatively, if you want the cutting edge code, you can check out
the GitHub repos at https://github.com/miarec/miarec_ftpfs

## Opening a S3FS

Open an S3FS by explicitly using the constructor:

```python
from fs.ftpfs import FTPFS
FTPFS("demo.wftpserver.com")
```

You can also use a non-anonymous username, and optionally a
password, even within a FS URL::

```python
ftp_fs = FTPFS("test.rebex.net", user="demo", passwd="password")
```

Connecting via a proxy is supported. If using a FS URL, the proxy
URL will need to be added as a URL parameter::

```python
ftp_fs = FTPFS("ftp.ebi.ac.uk", proxy="test.rebex.net")
```

## Testing

Automated unit tests are run on [GitHub Actions](https://github.com/miarec/miarec_s3fs/actions)

To run the tests locally, do the following.

Install Docker on local machine.

Create activate python virtual environment:

    python -m vevn venv
    source venv\bin\activate

Install the project and test dependencies:

    pip install -e ".[test]"

Run tests:

    pytest

## Documentation

- [PyFilesystem Wiki](https://www.pyfilesystem.org)
- [PyFilesystem Reference](https://docs.pyfilesystem.org/en/latest/reference/base.html)
