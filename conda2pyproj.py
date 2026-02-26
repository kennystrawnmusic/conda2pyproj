from sys import version_info
from json import loads, JSONDecodeError
from yaml import safe_load
from tomli_w import dump
from subprocess import run, CalledProcessError
from pathlib import Path
from argparse import ArgumentParser

def get_all_conda_channels():
    """Retrieves all configured conda channels via CLI."""
    try:
        # --json flag makes parsing reliable
        result = run(
            ["conda", "config", "--show", "channels", "--json"],
            capture_output=True, text=True, check=True, shell=True
        )
        config_data = loads(result.stdout)

        # Returns the list of channels from the 'channels' key
        return config_data.get('channels')

    except (CalledProcessError, JSONDecodeError):
        # Fallback to safe defaults if the command fails
        return ['conda-forge', 'defaults']

def main():
    parser = ArgumentParser(description="Tool for automating the process of migrating from conda to UniDep")

    parser.add_argument("--project-name", required=True, help="Name of the Python project to create from the Conda environment")
    parser.add_argument("--version", default="0.1.0", help="(Optional) Version of the target project (default: 0.1.0)")
    
    args = parser.parse_args()

    try:
        # Using shell=True for Windows conda.bat compatibility
        result = run(
            ["conda", "env", "export", "--from-history"], 
            capture_output=True, text=True, check=True, shell=True
        )
        conda_env = safe_load(result.stdout)
    except CalledProcessError as e:
        print(f"Error: {e.stderr}")
        exit(1)

    all_channels = get_all_conda_channels()

    # Initialize UniDep-specific structure
    unidep_deps = []
    for dep in conda_env.get('dependencies', []):
        if isinstance(dep, str):
            name = dep.split('=')[0]
            if name != 'python':
                unidep_deps.append(name)
        elif isinstance(dep, dict) and 'pip' in dep:
            for pip_dep in dep['pip']:
                # UniDep format for pip-only dependencies
                unidep_deps.append({"pip": pip_dep})

    pyproject = {
        "project": {
            "name": args.project_name,
            "version": args.version,
            # UniDep will automatically populate this field during build/install
            "dynamic": ["dependencies"],
            "requires-python": f">={version_info.major}.{version_info.minor}"
        },
        "tool": {
            "unidep": {
                "channels": all_channels,
                "dependencies": unidep_deps
            }
        },
        "build-system": {
            "requires": ["setuptools", "unidep"],
            "build-backend": "setuptools.build_meta"
        }
    }

    toml_dir = Path(args.project_name)
    toml_dir.mkdir(exist_ok=True)
    
    toml_file = toml_dir / "pyproject.toml"

    with open(toml_file, 'wb') as f:
        dump(pyproject, f)

    print(f"Successfully created UniDep-managed {toml_file}")

if __name__ == '__main__':
    main()
