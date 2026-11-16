"""Run tests using a workspace-local, loopback-only PostgreSQL cluster.

Downloads the official EDB portable binaries only with --download. No Windows
service is installed; the test server is stopped in finally. Data is under .qa/.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".qa" / "postgres"


def run(args, **kwargs):
    # pg_ctl's background server can inherit stdout. A file avoids waiting for
    # EOF on a pipe that remains open for the server's entire lifetime.
    output = WORK / "command-output.log"
    with output.open("wb") as stream:
        result = subprocess.run([str(a) for a in args], cwd=ROOT,
            stdout=stream, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, **kwargs)
    content = output.read_bytes()
    sys.stdout.buffer.write(content)
    sys.stdout.buffer.flush()
    with (WORK / "acceptance.log").open("ab") as log:
        log.write(content)
    result.check_returncode()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--stop", action="store_true", help="Stop only this workspace's test cluster")
    parser.add_argument("labels", nargs="*", default=["sales.test_postgresql"])
    options = parser.parse_args()
    binaries = WORK / "pgsql" / "bin"
    if options.stop:
        run([binaries / "pg_ctl.exe", "-D", WORK / "data", "-m", "fast", "-w", "stop"])
        return
    if not (binaries / "pg_ctl.exe").exists():
        if not options.download:
            parser.error("Portable binaries missing; use --download or configure config.postgresql_test_settings.")
        WORK.mkdir(parents=True, exist_ok=True)
        html = urllib.request.urlopen("https://www.enterprisedb.com/download-postgresql-binaries", timeout=60).read().decode()
        matches = re.findall(r'Version (?:<!-- -->)?17\.\d+</span>.*?href="(https://sbp\.enterprisedb\.com/getfile\.jsp\?fileid=\d+)"', html, re.S)
        if not matches:
            raise RuntimeError("Official PostgreSQL 17 binary link not found on EDB download page")
        url = matches[0]
        archive = WORK / "binaries.zip"
        print("Downloading", url, flush=True)
        urllib.request.urlretrieve(url, archive)
        print("Archive SHA256:", hashlib.sha256(archive.read_bytes()).hexdigest(), flush=True)
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                relative = Path(info.filename)
                destination = (WORK / relative).resolve()
                if not destination.is_relative_to(WORK.resolve()):
                    raise RuntimeError("Archive path escapes workspace")
                if relative.parts[:2] in (("pgsql", "bin"), ("pgsql", "lib"), ("pgsql", "share")):
                    bundle.extract(info, WORK)
    data = WORK / "data"
    if not (data / "PG_VERSION").exists():
        run([binaries / "initdb.exe", "-D", data, "-U", "erp_test", "-A", "trust", "--encoding=UTF8", "--locale=C"])
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    run([binaries / "pg_ctl.exe", "-D", data, "-l", WORK / "postgres.log", "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"])
    try:
        env = {**os.environ, "TEST_PG_HOST": "127.0.0.1", "TEST_PG_PORT": str(port),
            "TEST_PG_USER": "erp_test", "TEST_PG_PASSWORD": "", "TEST_PG_DATABASE": "postgres"}
        run([sys.executable, "manage.py", "test", *options.labels,
            "--settings=config.postgresql_test_settings", "--noinput"], env=env)
    finally:
        run([binaries / "pg_ctl.exe", "-D", data, "-m", "fast", "-w", "stop"])


if __name__ == "__main__":
    main()
