from sys import version_info
from json import loads, JSONDecodeError
from yaml import safe_load
from tomli_w import dump
from subprocess import run, CalledProcessError
from pathlib import Path
from argparse import ArgumentParser

# The build backend script that lives in the target project
HOOK_FILE_TEMPLATE = """
import shutil
import os
from pathlib import Path
from subprocess import run as _run
from setuptools import build_meta as _orig

# PEP 517 Required Hooks
prepare_metadata_for_build_wheel = _orig.prepare_metadata_for_build_wheel
build_sdist = _orig.build_sdist
get_requires_for_build_wheel = _orig.get_requires_for_build_wheel

def get_explicit_conda_urls():
    print("[*] Fetching explicit conda URLs...")
    res = _run(["conda", "list", "--explicit"], capture_output=True, text=True, shell=True)
    return [line.strip() for line in res.stdout.splitlines() if line.startswith("https://")]

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    print("[*] Custom Build Hook: Starting Conda-to-Wheel conversion...")
    
    temp_wheel_dir = Path("portable_wheels")
    temp_wheel_dir.mkdir(exist_ok=True)
    
    urls = get_explicit_conda_urls()
    if urls:
        for url in urls:
            pkg_name = url.split('/')[-1]
            print(f"--- Pressing: {pkg_name} ---")
            _run(f"conda press --skip-python --fatten {url}", shell=True)

        for wheel in Path(".").glob("*.whl"):
            shutil.move(str(wheel), str(temp_wheel_dir / wheel.name))
    
    # Run the real build
    result = _orig.build_wheel(wheel_directory, config_settings, metadata_directory)
    
    # Post-build Cleanup: Remove the temporary wheels directory
    if temp_wheel_dir.exists():
        print(f"[*] Cleaning up temporary wheels in {temp_wheel_dir}...")
        shutil.rmtree(temp_wheel_dir)
        
    return result
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

    blacklist = {"python", "_python_abi3_support"}

    for dep in conda_env.get('dependencies', []):
        if isinstance(dep, str):
            name = dep.split('=')[0]
            if name not in blacklist:
                unidep_deps.append(name)
        elif isinstance(dep, dict) and 'pip' in dep:
            for pip_dep in dep['pip']:
                if pip_dep not in blacklist:
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

    print(f"Successfully generated project in: {target_dir.absolute()}")

if __name__ == '__main__':
    main()