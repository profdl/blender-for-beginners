"""Make the two install files in dist/:

    studio_app_template.zip      Blender menu > Install Application Template...
    lumber_studio-<version>.zip  Preferences > Get Extensions > Install from Disk...

Run from the repo root:  python3 tools/package.py
"""
import os
import re
import zipfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST = os.path.join(REPO, "dist")
SKIP = ("__pycache__", ".pyc", ".blend1", ".DS_Store")


def _files(folder):
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in sorted(filenames):
            if not f.endswith(SKIP):
                yield os.path.join(dirpath, f)


def zip_folder(folder, zip_path, prefix):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in _files(folder):
            z.write(path, os.path.join(prefix, os.path.relpath(path, folder)))
    print("wrote", zip_path)


def main():
    os.makedirs(DIST, exist_ok=True)
    # The template zip holds the template folder itself: studio/__init__.py ...
    zip_folder(os.path.join(REPO, "app_template", "studio"),
               os.path.join(DIST, "studio_app_template.zip"), "studio")
    manifest = open(os.path.join(REPO, "lumber_studio", "blender_manifest.toml")).read()
    version = re.search(r'^version = "([^"]+)"', manifest, re.M).group(1)
    # An extension zip has blender_manifest.toml at its top level
    zip_folder(os.path.join(REPO, "lumber_studio"),
               os.path.join(DIST, f"lumber_studio-{version}.zip"), "")


if __name__ == "__main__":
    main()
