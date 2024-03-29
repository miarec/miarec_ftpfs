
from typing import Tuple
import random
from OpenSSL import crypto
import socket
from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler, SSLConnection, SSL
from pyftpdlib.test import ThreadedTestFTPd


def generate_tls_cert_legacy() -> Tuple[crypto.PKey, crypto.X509]:
    """
    Generate a private key and X.509 certificate using PyOpenSSL package.

    Based on https://nachtimwald.com/2019/11/14/python-self-signed-cert-gen/
    """
    pkey = crypto.PKey()
    pkey.generate_key(crypto.TYPE_RSA, 2048)

    x509 = crypto.X509()
    subject = x509.get_subject()
    subject.commonName = socket.gethostname()
    x509.set_issuer(subject)
    x509.gmtime_adj_notBefore(0)
    x509.gmtime_adj_notAfter(5*365*24*60*60)
    x509.set_pubkey(pkey)
    x509.set_serial_number(random.randrange(100000))
    x509.set_version(2)
    x509.add_extensions([
        crypto.X509Extension(b'subjectAltName', False,
            ','.join([
                'DNS:%s' % socket.gethostname(),
                'DNS:*.%s' % socket.gethostname(),
                'DNS:localhost',
                'DNS:*.localhost']).encode()),
        crypto.X509Extension(b"basicConstraints", True, b"CA:false")])

    x509.sign(pkey, 'SHA256')

    # return (crypto.dump_certificate(crypto.FILETYPE_PEM, x509),
    #    crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))

    return (pkey, x509)


def generate_tls_cert() -> Tuple[crypto.PKey, crypto.X509]:
    """
    Generate a private key and X.509 certificate using Cryptography package.

    Based on https://nachtimwald.com/2019/11/14/python-self-signed-cert-gen/
    """
    import datetime
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.x509.oid import NameOID

    one_day = datetime.timedelta(1, 0, 0)
    private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend())
    public_key = private_key.public_key()

    builder = x509.CertificateBuilder()
    builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname())]))
    builder = builder.issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname())]))
    builder = builder.not_valid_before(datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(datetime.datetime.today() + (one_day*365*5))
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(socket.gethostname()),
            x509.DNSName('*.%s' % socket.gethostname()),
            x509.DNSName('localhost'),
            x509.DNSName('*.localhost'),
        ]),
        critical=False)
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=default_backend())

    #return (certificate.public_bytes(serialization.Encoding.PEM),
    #    private_key.private_bytes(serialization.Encoding.PEM,
    #        serialization.PrivateFormat.PKCS8,
    #        serialization.NoEncryption()))

    return (
        crypto.PKey.from_cryptography_key(private_key),
        crypto.X509.from_cryptography(certificate)
    )



class ImplicitTLS_FTPHandler(SSLConnection, FTPHandler):
    """A FTPHandler subclass supporting Implicit TLS/SSL.

    Based on the pyftdlib's TLS_FTPHandler and
    old email thread https://github.com/giampaolo/pyftpdlib/issues/160

    SSL-specific options:

        - (string) certfile:
        the path to the file which contains a certificate to be
        used to identify the local side of the connection.
        This  must always be specified, unless context is provided
        instead.

        - (string) keyfile:
        the path to the file containing the private RSA key;
        can be omitted if certfile already contains the private
        key (defaults: None).

        - (int) ssl_protocol:
        the desired SSL protocol version to use. This defaults to
        PROTOCOL_SSLv23 which will negotiate the highest protocol
        that both the server and your installation of OpenSSL
        support.

        - (int) ssl_options:
        specific OpenSSL options. These default to:
        SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3| SSL.OP_NO_COMPRESSION
        which are all considered insecure features.
        Can be set to None in order to improve compatibility with
        older (insecure) FTP clients.

        - (instance) ssl_context:
        a SSL Context object previously configured; if specified
        all other parameters will be ignored.
        (default None).
    """

    certfile = None
    keyfile = None
    ssl_protocol = SSL.SSLv23_METHOD
    # - SSLv2 is easily broken and is considered harmful and dangerous
    # - SSLv3 has several problems and is now dangerous
    # - Disable compression to prevent CRIME attacks for OpenSSL 1.0+
    #   (see https://github.com/shazow/urllib3/pull/309)
    ssl_options = SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3
    if hasattr(SSL, "OP_NO_COMPRESSION"):
        ssl_options |= SSL.OP_NO_COMPRESSION
    ssl_context = None

    def __init__(self, conn, server, ioloop=None):
        super().__init__(conn, server, ioloop)
        if not self.connected:
            return
        self.ssl_context = self.get_ssl_context()

    def __repr__(self):
        return FTPHandler.__repr__(self)

    @classmethod
    def get_ssl_context(cls):
        if cls.ssl_context is None:
            if cls.certfile is None:
                raise ValueError("at least certfile must be specified")
            cls.ssl_context = SSL.Context(cls.ssl_protocol)
            cls.ssl_context.use_certificate_chain_file(cls.certfile)
            if not cls.keyfile:
                cls.keyfile = cls.certfile
            cls.ssl_context.use_privatekey_file(cls.keyfile)
            if cls.ssl_options:
                cls.ssl_context.set_options(cls.ssl_options)
        return cls.ssl_context

    def close(self):
        SSLConnection.close(self)
        FTPHandler.close(self)

    def handle_failed_ssl_handshake(self):
        # TLS/SSL handshake failure, probably client's fault which
        # used a SSL version different from server's.
        # We can't rely on the control connection anymore so we just
        # disconnect the client without sending any response.
        self.log("SSL handshake failed.")
        self.close()

    def ftp_AUTH(self, arg):
        self.respond("550 not supposed to be used with implicit SSL.")

    #def ftp_PROT(self, arg):
    #    self.respond("550 not supposed to be used with implicit SSL.")

    def handle(self):
        self.secure_connection(self.ssl_context)

    def handle_ssl_established(self):
        self.log("SSL is established (handle_ssl_established)")
        FTPHandler.handle(self)


class TLS_ThreadedTestFTPd(ThreadedTestFTPd):
    """A threaded FTP server over TLS.
    """

    def __init__(self, addr=None, implicit_tls=False):
        if implicit_tls:
            self.handler = ImplicitTLS_FTPHandler
        else:
            self.handler = TLS_FTPHandler

        self.handler.tls_data_required = True     # client must issue "AUTH TLS" before USER/PASS
        self.handler.tls_control_required = True  # client must issue PROT before PASS or PORT

        # -------------------------------------
        # Generate self-signed SSL certificate
        # -------------------------------------
        ssl_context = SSL.Context(SSL.TLSv1_2_METHOD)
        (pkey, cert) = generate_tls_cert()
        ssl_context.use_privatekey(pkey)
        ssl_context.use_certificate(cert)
        self.handler.ssl_context = ssl_context

        super().__init__(addr)



