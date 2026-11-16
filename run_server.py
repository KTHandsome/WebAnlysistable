from waitress import serve
from app import app

serve(
    app,
    host="0.0.0.0",
    port=80,
    trusted_proxy="127.0.0.1",
    trusted_proxy_count=1,
    trusted_proxy_headers={"x-forwarded-proto"},
    clear_untrusted_proxy_headers=True,
)