from sys import version_info
from json import loads, JSONDecodeError
from yaml import safe_load
from tomli_w import dump
from subprocess import run, CalledProcessError
from pathlib import Path
from argparse import ArgumentParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def package_exists_on_pypi(package_name):
    """Checks if a package exists on PyPI with a proper User-Agent."""
    normalized_name = package_name.replace("_", "-")
    url = f"https://pypi.org/pypi/{normalized_name}/json"
    
    # PyPI blocks basic urllib/python User-Agents frequently
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"}
    try:
        req = Request(url, headers=headers, method="HEAD")
        with urlopen(req, timeout=5) as response:
            return response.status == 200
    except (HTTPError, URLError) as e:
        return False
    except Exception:
        return False

HOOK_FILE_TEMPLATE = """
import shutil
import os
from pathlib import Path
from subprocess import run as _run
from setuptools import build_meta as _orig

# PEP 517 Required Hooks
prepare_metadata_for_build_wheel = _orig.prepare_metadata_for_build_wheel
build_sdist = _orig.build_sdist

def get_explicit_conda_urls():
    print("[*] Hook: Fetching explicit conda URLs...")
    res = _run(["conda", "list", "--explicit"], capture_output=True, text=True, shell=True)
    return [line.strip() for line in res.stdout.splitlines() if line.startswith("https://")]

def run_conda_press():
    temp_wheel_dir = Path("portable_wheels")
    if temp_wheel_dir.exists():
        return
        
    temp_wheel_dir.mkdir(exist_ok=True)
    urls = get_explicit_conda_urls()
    
    if urls:
        print("[*] Hook: Starting Conda-to-Wheel conversion...")
        for url in urls:
            pkg_name_raw = url.split('/')[-1]
            base_name = pkg_name_raw.split('-')[0]
            print(f"--- Pressing: {base_name} ---")
            _run(f"conda press --skip-python --fatten {url}", shell=True)

            # Normalization for pip resolver
            for wheel in Path(".").glob(f"{base_name}*.whl"):
                target_path = temp_wheel_dir / f"{base_name}-0.1.0-py3-none-any.whl"
                shutil.move(str(wheel), str(target_path))

def get_requires_for_build_wheel(config_settings=None):
    run_conda_press()
    return _orig.get_requires_for_build_wheel(config_settings)

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    run_conda_press()
    temp_wheel_dir = Path("portable_wheels")
    try:
        return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)
    finally:
        if temp_wheel_dir.exists():
            print(f"[*] Hook: Cleaning up {temp_wheel_dir}...")
            shutil.rmtree(temp_wheel_dir)
"""

def get_all_conda_channels():
    try:
        result = run(["conda", "config", "--show", "channels", "--json"], capture_output=True, text=True, check=True, shell=True)
        return loads(result.stdout).get('channels')
    except (CalledProcessError, JSONDecodeError):
        return ['conda-forge', 'defaults']

def main():
    parser = ArgumentParser(description="Conda to pyproject.toml/build hook converter")

    parser.add_argument("--project-name", required=True)
    parser.add_argument("--project-description", required=True)
    parser.add_argument("--version", default="0.1.0")

    args = parser.parse_args()

    try:
        result = run(
            ["conda", "env", "export"], 
            capture_output=True, text=True, check=True, shell=True
        )
        conda_env = safe_load(result.stdout)
    except CalledProcessError as e:
        print(f"Error: {e.stderr}"); exit(1)

    all_channels = get_all_conda_channels()

    unidep_deps = []

    # Filter out system binaries and conda internals
    blacklist = {"python", "_python_abi3_support", "conda", "mamba", "pip", "ca-certificates", "openssl", "vc", "vs2015_runtime"}

    for dep in conda_env.get('dependencies', []):
        if isinstance(dep, str):
            name = dep.split('=')[0]
            if name in blacklist:
                continue
            
            if package_exists_on_pypi(name):
                print(f"  [PyPI] {name}")
                unidep_deps.append(name)
            else:
                # Direct file reference for the build hook to fulfill
                print(f"  [Conda-Only] {name} -> mapping to local wheel")
                unidep_deps.append(f"{name} @ file://./portable_wheels/{name}-0.1.0-py3-none-any.whl")
        
        elif isinstance(dep, dict) and 'pip' in dep:
            for pip_dep in dep['pip']:
                unidep_deps.append({"pip": pip_dep})

    pyproject = {
        "project": {
            "name": args.project_name,
            "version": args.version,
            "description": args.project_description,
            "dynamic": ["dependencies"],
            "requires-python": f">={version_info.major}.{version_info.minor}",
        },
        "tool": {
            "unidep": {"channels": all_channels, "dependencies": unidep_deps}
        },
        "build-system": {
            # conda-press is required at build-time to run the hooks
            "requires": ["setuptools", "unidep", "conda-press", "tomli-w", "pyyaml"],
            "build-backend": "build_hooks",
            "backend-path": ["."]
        }
    }

    target_dir = Path(args.project_name)
    target_dir.mkdir(exist_ok=True)
    
    with open(target_dir / "pyproject.toml", 'wb') as f:
        dump(pyproject, f)

    with open(target_dir / "build_hooks.py", 'w', encoding='utf-8') as f:
        f.write(HOOK_FILE_TEMPLATE.strip())

    print(f"\n[DONE] Project generated in: {target_dir.absolute()}")
    print("To install: cd into the folder and run 'pip install -e .'")

if __name__ == '__main__':
    main()