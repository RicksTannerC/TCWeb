"""Guards on how the app is launched. Waitress drops X-Forwarded-* headers unless it is told
which proxy to trust, so without these flags the site never knows it is served over HTTPS."""

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent


class WaitressProxyFlagsTests(SimpleTestCase):
    FLAGS = ("--trusted-proxy=127.0.0.1", "--trusted-proxy-headers=x-forwarded-proto")

    def test_the_supervisor_launches_waitress_with_the_proxy_flags(self):
        script = (ROOT / "deploy" / "run_server.ps1").read_text(encoding="utf-8")
        for flag in self.FLAGS:
            self.assertIn(flag, script)

    def test_the_readme_launch_command_has_them_too(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for flag in self.FLAGS:
            self.assertIn(flag, readme)

    def test_the_proxy_header_setting_is_still_configured_for_production(self):
        settings_py = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertIn('SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")', settings_py)
