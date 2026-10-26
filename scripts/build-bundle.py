#!/usr/bin/env python3
# Build the bitfocus-modules-data bundles from the Companion module store.
#
# Since March 2026 bitfocus/companion-bundled-modules no longer receives module
# builds in git: they are published to developer.bitfocus.io instead. This does
# what Companion's own tools/prepare_offline_module_bundle.mts does: take the
# newest non-deprecated release of every connection module, then add the Node.js
# runtimes those modules declare, once per platform.
#
# Usage: build-bundle.py <out-dir> [--max-api-major N] [--include-all-licenses]
# Writes <out-dir>/bitfocus-modules-data-<platform>.zip and <out-dir>/versions.txt.

import argparse, io, json, os, shutil, subprocess, sys, tarfile, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor

API = "https://developer.bitfocus.io/api/v1/companion/modules"
UA = {"User-Agent": "ossia score bitfocus-modules-data builder"}

# Node archive suffix per release platform name; the names match the v1.0.3 assets.
PLATFORMS = {
    "linux-x64": "linux-x64.tar.xz",
    "linux-arm64": "linux-arm64.tar.xz",
    "darwin-x64": "darwin-x64.tar.gz",
    "darwin-arm64": "darwin-arm64.tar.gz",
    "win-x64": "win-x64.zip",
}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()

def api_major(v):
    try:
        return int(v.split(".")[0])
    except ValueError:
        return 0

def pick_version(name, max_major, all_licenses):
    info = json.loads(get(f"{API}/connection/{name}"))
    ok = [v for v in info["versions"]
          if v.get("tarUrl") and api_major(v["apiVersion"]) <= max_major]
    # Newest first, as Companion assumes: prefer a release, fall back to a prerelease.
    v = next((v for v in ok if not v["isPrerelease"]), None) or next(iter(ok), None)
    if v is None:
        return None
    if not all_licenses and v.get("licenseCategory") in ("COPYLEFT", "UNKNOWN"):
        return None
    return v

def fetch_module(name, v, dest):
    data = get(v["tarUrl"])
    tmp = os.path.join(dest, f".{name}.tmp")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        t.extractall(tmp, filter="data")
    # Newer packages nest everything under one directory (the module name or
    # "pkg"), older ones are flat. Normalise both to <dest>/<name>.
    top = os.path.join(dest, name)
    if os.path.isdir(os.path.join(tmp, "companion")):
        os.rename(tmp, top)
    else:
        (inner,) = os.listdir(tmp)
        os.rename(os.path.join(tmp, inner), top)
        os.rmdir(tmp)
    with open(os.path.join(top, "companion", "manifest.json")) as f:
        return json.load(f)["runtime"]["type"]

def latest_node(major):
    index = json.loads(get("https://nodejs.org/dist/index.json"))
    return next(r["version"].lstrip("v") for r in index
                if r["version"].startswith(f"v{major}."))

def fetch_node(version, suffix, dest):
    url = f"https://nodejs.org/dist/v{version}/node-v{version}-{suffix}"
    data = get(url)
    tmp = dest + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    if suffix.endswith(".zip"):
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            t.extractall(tmp, filter="tar")
    (inner,) = os.listdir(tmp)
    os.rename(os.path.join(tmp, inner), dest)
    os.rmdir(tmp)
    # Same pruning as create-release.sh: score only runs the node binary.
    for sub in ("include", "lib", "share", "node_modules"):
        shutil.rmtree(os.path.join(dest, sub), ignore_errors=True)
    for root, dirs, files in os.walk(dest):
        for f in files:
            if f.startswith(("npm", "npx", "corepack")):
                os.remove(os.path.join(root, f))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--max-api-major", type=int, default=1)
    ap.add_argument("--include-all-licenses", action="store_true")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    stage = os.path.join(out, "stage", "bitfocus-modules-data")
    mods = os.path.join(stage, "companion-bundled-modules")
    shutil.rmtree(os.path.join(out, "stage"), ignore_errors=True)
    os.makedirs(mods)

    listing = json.loads(get(f"{API}/connection"))["modules"]
    names = sorted(m["id"] for m in listing if not m.get("deprecationReason"))
    print(f"{len(names)} non-deprecated connection modules in the store")

    with ThreadPoolExecutor(10) as ex:
        picked = dict(zip(names, ex.map(
            lambda n: pick_version(n, args.max_api_major, args.include_all_licenses), names)))
    picked = {n: v for n, v in picked.items() if v}
    with ThreadPoolExecutor(10) as ex:
        runtimes = dict(zip(picked, ex.map(lambda n: fetch_module(n, picked[n], mods), picked)))

    majors = sorted({int(t.removeprefix("node")) for t in runtimes.values()})
    nodes = {m: latest_node(m) for m in majors}
    print("node runtimes:", nodes)

    with open(os.path.join(out, "versions.txt"), "w") as f:
        for m, v in nodes.items():
            f.write(f"node{m} {v}\n")
        for n in sorted(picked):
            f.write(f"{n} {picked[n]['id']} api{picked[n]['apiVersion']}\n")

    shutil.copy(os.path.join(os.path.dirname(__file__), "..", "addon.json"), stage)
    for plat, suffix in PLATFORMS.items():
        rt = os.path.join(stage, "node-runtime")
        shutil.rmtree(rt, ignore_errors=True)
        os.makedirs(rt)
        for v in nodes.values():
            fetch_node(v, suffix, os.path.join(rt, v))
        zip_path = os.path.join(out, f"bitfocus-modules-data-{plat}.zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        # 7z keeps the unix exec bits on node, which zipfile.write would too, but
        # it is several times faster on ~40k files.
        subprocess.run(["7z", "a", "-bd", "-mx=7", zip_path, "bitfocus-modules-data"],
                       cwd=os.path.dirname(stage), check=True, stdout=subprocess.DEVNULL)
        print(f"{zip_path}: {os.path.getsize(zip_path) // 1_000_000} MB")

if __name__ == "__main__":
    sys.exit(main())
