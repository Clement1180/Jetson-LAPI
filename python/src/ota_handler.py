import hashlib
import logging
import os
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request

log = logging.getLogger("lapi.ota")


class OTAHandler:
    def __init__(self, install_dir: str = "/opt/lapi",
                 ota_dir: str = "/var/lib/lapi/ota"):
        self._install_dir = install_dir
        self._ota_dir = ota_dir
        self._backup_dir = os.path.join(ota_dir, "backup")
        self._lock = threading.Lock()
        os.makedirs(self._ota_dir, exist_ok=True)
        os.makedirs(self._backup_dir, exist_ok=True)

    def handle_update(self, payload: dict):
        url = payload.get("url", "")
        sha256 = payload.get("sha256", "")
        version = payload.get("version", "")
        if not url or not sha256 or not version:
            log.error("Payload OTA incomplet, ignore")
            return
        if not self._lock.acquire(blocking=False):
            log.warning("Mise a jour OTA deja en cours, ignore")
            return
        log.info(f"OTA demandee: version={version}")
        t = threading.Thread(target=self._do_update, args=(url, sha256, version),
                             daemon=True)
        t.start()

    def _do_update(self, url: str, expected_sha256: str, version: str):
        archive_path = os.path.join(self._ota_dir, f"lapi-{version}.tar.gz")
        extract_dir = os.path.join(self._ota_dir, f"lapi-{version}")
        backup_path = os.path.join(self._backup_dir, f"python_{int(time.time())}")
        try:
            self._download(url, archive_path)
            self._verify(archive_path, expected_sha256)
            self._extract(archive_path, extract_dir)
            self._backup(backup_path)
            self._install(extract_dir)
            self._prune_backups(keep=3)
            log.info(f"OTA {version} installee, redemarrage du service...")
            subprocess.run(["sudo", "systemctl", "restart", "lapi.service"],
                           timeout=30)
        except Exception as e:
            log.error(f"OTA {version} echouee: {e}")
            if os.path.isdir(backup_path):
                self._rollback(backup_path)
        finally:
            for path in (archive_path, extract_dir):
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.isfile(path):
                    os.remove(path)
            self._lock.release()

    def _download(self, url: str, dest: str):
        log.info(f"Telechargement: {url}")
        tmp = dest + ".tmp"
        try:
            urllib.request.urlretrieve(url, tmp)
            os.rename(tmp, dest)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        log.info(f"Telecharge: {os.path.getsize(dest)} octets")

    def _verify(self, path: str, expected: str):
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        if actual != expected:
            raise ValueError(f"SHA256 invalide: attendu {expected[:16]}..., obtenu {actual[:16]}...")
        log.info("SHA256 verifie")

    def _extract(self, archive: str, dest: str):
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(dest, filter="data")
        log.info(f"Extrait dans {dest}")

    def _backup(self, backup_path: str):
        src = os.path.join(self._install_dir, "python")
        if os.path.isdir(src):
            shutil.copytree(src, backup_path)
            log.info(f"Backup dans {backup_path}")

    def _install(self, extract_dir: str):
        entries = os.listdir(extract_dir)
        source = extract_dir
        if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
            source = os.path.join(extract_dir, entries[0])

        install_script = os.path.join(source, "install.sh")
        if os.path.isfile(install_script):
            log.info("Execution du script d'installation personnalise")
            subprocess.run(["bash", install_script], cwd=source, check=True, timeout=120)
            return

        dest_python = os.path.join(self._install_dir, "python")
        src_python = os.path.join(source, "python")
        if os.path.isdir(os.path.join(src_python, "src")):
            src_dir = os.path.join(src_python, "src")
            dst_dir = os.path.join(dest_python, "src")
            if os.path.isdir(dst_dir):
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)

        service_py = os.path.join(src_python, "service.py")
        if os.path.isfile(service_py):
            shutil.copy2(service_py, os.path.join(dest_python, "service.py"))

        requirements = os.path.join(src_python, "requirements.txt")
        if os.path.isfile(requirements):
            shutil.copy2(requirements, os.path.join(dest_python, "requirements.txt"))
            venv_pip = os.path.join(self._install_dir, "venv", "bin", "pip")
            if os.path.isfile(venv_pip):
                subprocess.run([venv_pip, "install", "-r", requirements, "-q"],
                               check=True, timeout=120)

        src_models = os.path.join(source, "models")
        if os.path.isdir(src_models):
            dst_models = os.path.join(self._install_dir, "models")
            for f in os.listdir(src_models):
                shutil.copy2(os.path.join(src_models, f), os.path.join(dst_models, f))

        log.info("Fichiers installes")

    def _rollback(self, backup_path: str):
        dest = os.path.join(self._install_dir, "python")
        log.warning(f"Rollback depuis {backup_path}")
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(backup_path, dest)
        subprocess.run(["sudo", "systemctl", "restart", "lapi.service"],
                       timeout=30)

    def _prune_backups(self, keep: int = 3):
        backups = sorted(
            [d for d in os.listdir(self._backup_dir)
             if os.path.isdir(os.path.join(self._backup_dir, d))],
            reverse=True
        )
        for old in backups[keep:]:
            shutil.rmtree(os.path.join(self._backup_dir, old), ignore_errors=True)
            log.info(f"Ancien backup supprime: {old}")
