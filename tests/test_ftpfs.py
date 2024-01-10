# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

import calendar
import datetime
import os
import platform
import shutil
import socket
import tempfile
import time
import unittest
import uuid

try:
    from unittest import mock
except ImportError:
    import mock

from ftplib import error_perm, error_temp
from pyftpdlib.authorizers import DummyAuthorizer
from six import BytesIO, text_type

from fs import errors
from miarec_ftpfs import FTPFS, ftp_errors
from fs.opener import open_fs
import fs.path
from fs.subfs import SubFS
from fs.test import FSTestCases
from fs.subfs import ClosingSubFS

try:
    from pytest import mark
except ImportError:
    from . import mark

# Prevent socket timeouts from slowing tests too much
socket.setdefaulttimeout(1)


class TestFTPFSClass(unittest.TestCase):
    def test_parse_ftp_time(self):
        self.assertIsNone(FTPFS._parse_ftp_time("notreallyatime"))
        t = FTPFS._parse_ftp_time("19740705000000")
        self.assertEqual(t, 142214400)

    def test_parse_mlsx(self):
        info = list(
            FTPFS._parse_mlsx(["create=19740705000000;modify=19740705000000; /foo"])
        )[0]
        self.assertEqual(info["details"]["modified"], 142214400)
        self.assertEqual(info["details"]["created"], 142214400)

        info = list(FTPFS._parse_mlsx(["foo=bar; .."]))
        self.assertEqual(info, [])

    def test_parse_mlsx_type(self):
        lines = [
            "Type=cdir;Modify=20180731114724;UNIX.mode=0755; /tmp",
            "Type=pdir;Modify=20180731112024;UNIX.mode=0775; /",
            "Type=file;Size=331523;Modify=20180731112041;UNIX.mode=0644; a.csv",
            "Type=file;Size=368340;Modify=20180731112041;UNIX.mode=0644; b.csv",
        ]
        expected = [
            {
                "basic": {"name": "a.csv", "is_dir": False},
                "ftp": {
                    "type": "file",
                    "size": "331523",
                    "modify": "20180731112041",
                    "unix.mode": "0644",
                },
                "details": {"type": 2, "size": 331523, "modified": 1533036041},
            },
            {
                "basic": {"name": "b.csv", "is_dir": False},
                "ftp": {
                    "type": "file",
                    "size": "368340",
                    "modify": "20180731112041",
                    "unix.mode": "0644",
                },
                "details": {"type": 2, "size": 368340, "modified": 1533036041},
            },
        ]
        info = list(FTPFS._parse_mlsx(lines))
        self.assertEqual(info, expected)

    def test_opener(self):
        ftp_fs = open_fs("mftp://will:wfc@ftp.example.org")
        self.assertIsInstance(ftp_fs, FTPFS)
        self.assertEqual(ftp_fs.host, "ftp.example.org")

        ftps_fs = open_fs("mftps://will:wfc@ftp.example.org")
        self.assertIsInstance(ftps_fs, FTPFS)
        self.assertTrue(ftps_fs.tls)


class TestFTPErrors(unittest.TestCase):
    """Test the ftp_errors context manager."""

    def test_manager(self):
        mem_fs = open_fs("mem://")

        with self.assertRaises(errors.ResourceError):
            with ftp_errors(mem_fs, path="foo"):
                raise error_temp

        with self.assertRaises(errors.OperationFailed):
            with ftp_errors(mem_fs):
                raise error_temp

        with self.assertRaises(errors.InsufficientStorage):
            with ftp_errors(mem_fs):
                raise error_perm("552 foo")

        with self.assertRaises(errors.ResourceNotFound):
            with ftp_errors(mem_fs):
                raise error_perm("501 foo")

        with self.assertRaises(errors.PermissionDenied):
            with ftp_errors(mem_fs):
                raise error_perm("999 foo")

    def test_manager_with_host(self):
        mem_fs = open_fs("mem://")
        mem_fs.host = "ftp.example.com"

        with self.assertRaises(errors.RemoteConnectionError) as err_info:
            with ftp_errors(mem_fs):
                raise EOFError
        expected_message = "lost connection to ftp.example.com"
        self.assertEqual(str(err_info.exception)[:len(expected_message)], expected_message)

        with self.assertRaises(errors.RemoteConnectionError) as err_info:
            with ftp_errors(mem_fs):
                raise socket.error
        expected_message = "unable to connect to ftp.example.com"
        self.assertEqual(str(err_info.exception)[:len(expected_message)], expected_message)


@mark.slow
@unittest.skipIf(platform.python_implementation() == "PyPy", "ftp unreliable with PyPy")
class TestFTPFS(FSTestCases, unittest.TestCase):
    proto = "mftp"
    user = "user"
    pasw = "1234"

    @classmethod
    def startServer(cls, temp_dir):
        from pyftpdlib.test import ThreadedTestFTPd

        server = ThreadedTestFTPd()
        server.shutdown_after = -1
        server.handler.authorizer = DummyAuthorizer()
        server.handler.authorizer.add_user(
            cls.user, cls.pasw, temp_dir, perm="elradfmwT"
        )
        server.handler.authorizer.add_anonymous(temp_dir)
        server.start()

        # Don't know why this is necessary on Windows
        if platform.system() == "Windows":
            time.sleep(0.1)
        # Poll until a connection can be made
        if not server.is_alive():
            raise RuntimeError("could not start FTP TLS server.")

        return server

    @classmethod
    def stopServer(cls, server):
        server.stop()
        server.join(2.0)

    @classmethod
    def setUpClass(cls):
        super(TestFTPFS, cls).setUpClass()
        cls._temp_dir = tempfile.mkdtemp("ftpfs2tests")
        cls.server = cls.startServer(cls._temp_dir)

    @classmethod
    def tearDownClass(cls):
        cls.stopServer(cls.server)
        shutil.rmtree(cls._temp_dir)
        super(TestFTPFS, cls).tearDownClass()

    def make_fs(self):
        # Create unique sub-folder for each test (c) MiaRec
        self.ftp_fs = FTPFS(
            host=self.server.host,
            port=self.server.port,
            user=self.user,
            passwd=self.pasw,
            tls=True if self.proto.endswith('ftps') else False
        )
        self.test_folder = uuid.uuid4().hex
        self.ftp_fs.makedir(self.test_folder, recreate=True)
        return self.ftp_fs.opendir(self.test_folder, factory=ClosingSubFS)

        # Old code below doesn't support running tests simultaneiously as all tests share the same folder (c) MiaRec
        #return open_fs(
        #    "{}://{}:{}@{}:{}".format(
        #        self.proto, self.user, self.pasw, self.server.host, self.server.port
        #    )
        #)
        
    def tearDown(self):
        # On Windows, this may fail because files in this directory are still opened by FTP server
        # shutil.rmtree(self._temp_path)   
        # os.mkdir(self._temp_path)
        super(TestFTPFS, self).tearDown()

    def test_ftp_url(self):
        self.assertEqual(
            self.fs.geturl(""),
            "{}://{}:{}@{}:{}/{}".format(
                self.proto, self.user, self.pasw, self.server.host, self.server.port, self.test_folder
            ),
        )

    def test_geturl(self):
        self.fs.makedir("foo")
        self.fs.create("bar")
        self.fs.create("foo/bar")
        self.assertEqual(
            self.fs.geturl("foo"),
            "{}://{}:{}@{}:{}/{}/foo".format(
                self.proto, self.user, self.pasw, self.server.host, self.server.port, self.test_folder
            ),
        )
        self.assertEqual(
            self.fs.geturl("bar"),
            "{}://{}:{}@{}:{}/{}/bar".format(
                self.proto, self.user, self.pasw, self.server.host, self.server.port, self.test_folder
            ),
        )
        self.assertEqual(
            self.fs.geturl("foo/bar"),
            "{}://{}:{}@{}:{}/{}/foo/bar".format(
                self.proto, self.user, self.pasw, self.server.host, self.server.port, self.test_folder
            ),
        )

    def test_setinfo(self):
        # TODO: temporary test, since FSTestCases.test_setinfo is broken.
        self.fs.create("bar")
        original_modified = self.fs.getinfo("bar", ("details",)).modified
        new_modified = original_modified - datetime.timedelta(hours=1)
        new_modified_stamp = calendar.timegm(new_modified.timetuple())
        self.fs.setinfo("bar", {"details": {"modified": new_modified_stamp}})
        new_modified_get = self.fs.getinfo("bar", ("details",)).modified
        if original_modified.microsecond == 0 or new_modified_get.microsecond == 0:
            original_modified = original_modified.replace(microsecond=0)
            new_modified_get = new_modified_get.replace(microsecond=0)
        if original_modified.second == 0 or new_modified_get.second == 0:
            original_modified = original_modified.replace(second=0)
            new_modified_get = new_modified_get.replace(second=0)
        new_modified_get = new_modified_get + datetime.timedelta(hours=1)
        self.assertEqual(original_modified, new_modified_get)

    def test_host(self):
        fs = self.fs.delegate_fs()
        self.assertEqual(fs.host, self.server.host)

    def test_connection_error(self):
        fs = FTPFS("ftp.not.a.chance", timeout=1)
        with self.assertRaises(errors.RemoteConnectionError):
            fs.listdir("/")

        with self.assertRaises(errors.RemoteConnectionError):
            fs.makedir("foo")

        with self.assertRaises(errors.RemoteConnectionError):
            fs.open("foo.txt")

    def test_getmeta_unicode_path(self):
        self.assertTrue(self.fs.getmeta().get("unicode_paths"))
        fs = self.fs.delegate_fs()
        fs.features
        del fs.features["UTF8"]
        self.assertFalse(fs.getmeta().get("unicode_paths"))

    def test_getinfo_modified(self):
        fs = self.fs.delegate_fs()
        fs.features
        self.assertIn("MDTM", fs.features)
        self.fs.create("bar")
        mtime_detail = self.fs.getinfo("bar", ("basic", "details")).modified
        mtime_modified = self.fs.getmodified("bar")
        # Microsecond and seconds might not actually be supported by all
        # FTP commands, so we strip them before comparing if it looks
        # like at least one of the two values does not contain them.
        replacement = {}
        if mtime_detail.microsecond == 0 or mtime_modified.microsecond == 0:
            replacement["microsecond"] = 0
        if mtime_detail.second == 0 or mtime_modified.second == 0:
            replacement["second"] = 0
        self.assertEqual(
            mtime_detail.replace(**replacement), mtime_modified.replace(**replacement)
        )

    def test_opener_path(self):
        self.fs.makedir("foo")
        self.fs.writetext("foo/bar", "baz")
        ftp_fs = open_fs(
            "{}://user:1234@{}:{}/{}/foo".format(self.proto, self.server.host, self.server.port, self.test_folder)
        )
        self.assertIsInstance(ftp_fs, SubFS)
        self.assertEqual(ftp_fs.readtext("bar"), "baz")
        ftp_fs.close()

    def test_create(self):

        directory = fs.path.join("home", self.user, "test", "directory")
        base = "{}://user:1234@{}:{}/{}/foo".format(self.proto, self.server.host, self.server.port, self.test_folder)
        url = "{}/{}".format(base, directory)

        # Make sure unexisting directory raises `CreateFailed`
        with self.assertRaises(errors.CreateFailed):
            ftp_fs = open_fs(url)

        # Open with `create` and try touching a file
        with open_fs(url, create=True) as ftp_fs:
            ftp_fs.touch("foo")

        # Open the base filesystem and check the subdirectory exists
        with open_fs(base) as ftp_fs:
            self.assertTrue(ftp_fs.isdir(directory))
            self.assertTrue(ftp_fs.isfile(fs.path.join(directory, "foo")))

        # Open without `create` and check the file exists
        with open_fs(url) as ftp_fs:
            self.assertTrue(ftp_fs.isfile("foo"))

        # Open with create and check this does fail
        with open_fs(url, create=True) as ftp_fs:
            self.assertTrue(ftp_fs.isfile("foo"))

    def test_upload_connection(self):
        fs = self.fs.delegate_fs()
        with mock.patch.object(fs, "_manage_ftp") as _manage_ftp:
            self.fs.upload("foo", BytesIO(b"hello"))
        self.assertEqual(self.fs.readtext("foo"), "hello")
        _manage_ftp.assert_not_called()


class TestFTPFSNoMLSD(TestFTPFS):
    def make_fs(self):
        fs = super(TestFTPFSNoMLSD, self).make_fs()

        ftp_fs = fs.delegate_fs()
        ftp_fs.features
        del ftp_fs.features["MLST"]
        return fs

    def test_features(self):
        pass


@mark.slow
@unittest.skipIf(platform.python_implementation() == "PyPy", "ftp unreliable with PyPy")
class TestAnonFTPFS(TestFTPFS):
    proto = "mftp"
    user = "anonymous"
    pasw = ""

    @classmethod
    def startServer(cls, temp_dir):
        from pyftpdlib.test import ThreadedTestFTPd

        server = ThreadedTestFTPd()
        server.shutdown_after = -1
        server.handler.authorizer = DummyAuthorizer()
        server.handler.authorizer.add_anonymous(temp_dir, perm="elradfmw")
        server.start()

        # Don't know why this is necessary on Windows
        if platform.system() == "Windows":
            time.sleep(0.1)

        # Poll until a connection can be made
        if not server.is_alive():
            raise RuntimeError("could not start FTP TLS server.")

        return server


    def test_ftp_url(self):
        self.assertEqual(
            self.fs.geturl(""), "{}://{}:{}/{}".format(self.proto, self.server.host, self.server.port, self.test_folder)
        )

    def test_geturl(self):
        self.fs.makedir("foo")
        self.fs.create("bar")
        self.fs.create("foo/bar")
        self.assertEqual(
            self.fs.geturl("foo"),
            "{}://{}:{}/{}/foo".format(self.proto, self.server.host, self.server.port, self.test_folder),
        )
        self.assertEqual(
            self.fs.geturl("bar"),
            "{}://{}:{}/{}/bar".format(self.proto, self.server.host, self.server.port, self.test_folder),
        )
        self.assertEqual(
            self.fs.geturl("foo/bar"),
            "{}://{}:{}/{}/foo/bar".format(self.proto, self.server.host, self.server.port, self.test_folder),
        )

    def test_opener_path(self):
        self.fs.makedir("foo")
        self.fs.writetext("foo/bar", "baz")
        ftp_fs = open_fs(
            "{}://{}:{}/{}/foo".format(self.proto, self.server.host, self.server.port, self.test_folder)
        )
        self.assertIsInstance(ftp_fs, SubFS)
        self.assertEqual(ftp_fs.readtext("bar"), "baz")
        ftp_fs.close()

    def test_create(self):
        directory = fs.path.join("home", self.user, "test", "directory")
        base = "{}://{}:{}/{}/foo".format(self.proto, self.server.host, self.server.port, self.test_folder)
        url = "{}/{}".format(base, directory)

        # Make sure unexisting directory raises `CreateFailed`
        with self.assertRaises(errors.CreateFailed):
            ftp_fs = open_fs(url)

        # Open with `create` and try touching a file
        with open_fs(url, create=True) as ftp_fs:
            ftp_fs.touch("foo")

        # Open the base filesystem and check the subdirectory exists
        with open_fs(base) as ftp_fs:
            self.assertTrue(ftp_fs.isdir(directory))
            self.assertTrue(ftp_fs.isfile(fs.path.join(directory, "foo")))

        # Open without `create` and check the file exists
        with open_fs(url) as ftp_fs:
            self.assertTrue(ftp_fs.isfile("foo"))

        # Open with create and check this does fail
        with open_fs(url, create=True) as ftp_fs:
            self.assertTrue(ftp_fs.isfile("foo"))

    def test_setinfo(self):
        # For anonymous user, this test will fail, so we disable it (c) MiaRec
        # Anonymous user cannot change file attributes
        pass



@mark.slow
@unittest.skipIf(platform.python_implementation() == "PyPy", "ftp unreliable with PyPy")
class TestFTPFS_TLS(TestFTPFS):
    """FTP over TLS"""

    proto = "mftps"

    @classmethod
    def startServer(cls, temp_dir):
        from pyftpdlib.test import ThreadedTestFTPd
        from pyftpdlib.handlers import TLS_FTPHandler

        from OpenSSL import SSL
        from .helpers import generate_tls_cert

        (pkey, cert) = generate_tls_cert()

        ssl_protocol = SSL.TLSv1_2_METHOD
        ssl_context = SSL.Context(ssl_protocol)
        ssl_context.use_privatekey(pkey)
        ssl_context.use_certificate(cert)


        class TLS_ThreadedTestFTPd(ThreadedTestFTPd):
            """A threaded FTP server over TLS.
            """
            handler = TLS_FTPHandler
            handler.ssl_context = ssl_context


        server = TLS_ThreadedTestFTPd()
        server.shutdown_after = -1
        server.handler.authorizer = DummyAuthorizer()
        server.handler.authorizer.add_user(
            cls.user, cls.pasw, temp_dir, perm="elradfmwT"
        )
        server.handler.authorizer.add_anonymous(temp_dir)
        server.start()

        # Don't know why this is necessary on Windows
        if platform.system() == "Windows":
            time.sleep(0.1)
        # Poll until a connection can be made
        if not server.is_alive():
            raise RuntimeError("could not start FTP TLS server.")

        return server



