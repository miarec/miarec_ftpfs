import ftplib
import ssl


class ExplicitFTP_TLS(ftplib.FTP_TLS):
    def __init__(self, reuse_ssl_session=True, *args, **kwargs):
        self.reuse_ssl_session = reuse_ssl_session
        super().__init__(*args, **kwargs)

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            if self.reuse_ssl_session:
                # Support TLS session resumpion (possible in Python 3.6+ only)
                # SRC: https://stackoverflow.com/questions/14659154/ftpes-session-reuse-required
                conn = self.context.wrap_socket(conn,
                                                server_hostname=self.host,
                                                session=self.sock.session)
            else:
                conn = self.context.wrap_socket(conn,
                                                server_hostname=self.host)

        return conn, size


class ImplicitFTP_TLS(ExplicitFTP_TLS):
    """FTP_TLS subclass that automatically wraps sockets in SSL to support implicit FTPS."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        """Return the socket."""
        return self._sock

    @sock.setter
    def sock(self, value):
        """When modifying the socket, ensure that it is ssl wrapped."""
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value


    def prot_p(self):
        # do nothing as connection is already secured
        pass

    def prot_c(self):
        # do nothing as we use Implicit TLS
        pass