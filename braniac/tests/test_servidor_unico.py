import pytest

from braniac import server


def test_segundo_braniac_nao_ocupa_a_mesma_porta():
    a = server._ServidorUnico(("127.0.0.1", 0), server.BaseHTTPRequestHandler)
    try:
        with pytest.raises(OSError):
            server._ServidorUnico(("127.0.0.1", a.server_address[1]), server.BaseHTTPRequestHandler)
    finally:
        a.server_close()
