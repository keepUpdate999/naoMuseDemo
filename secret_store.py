"""Current-Windows-user DPAPI secrets, never rendered to the browser."""
import base64


def protect(value):
    import win32crypt
    return base64.b64encode(win32crypt.CryptProtectData(value.encode('utf-8'), 'nanoMuse demo', None, None, None, 1)).decode('ascii')


def unprotect(value):
    import win32crypt
    return win32crypt.CryptUnprotectData(base64.b64decode(value), None, None, None, 1)[1].decode('utf-8')
