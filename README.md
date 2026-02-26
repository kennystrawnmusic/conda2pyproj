# conda2pyproj: Conda-to-UniDep migration tool

Although miniconda3 is great when you're just learning, hence why Hack The Box uses it for the [AI Red Teamer job role path](https://academy.hackthebox.com/path/preview/ai-red-teamer), it has its limitations, specifically when it comes to portability: how do you reuse the code for a bigger project whilst ensuring all dependencies are the same?

To work around this problem, I scripted together this tool, which:
1. Autodetects the version of Python in the currently-active conda environment
2. Calls `conda env export` and captures the output
3. Enumerates all currently active conda channels
4. Creates a new project directory if one doesn't already exist
5. Automatically generates a UniDep-compatible `pyproject.toml` file containing the entire Conda environment

## Usage

The only required parameter is the name of the Python project to generate:

```
conda2pyproj --project-name test
```

Optionally, one can specify the version of the target package:

```
conda2pyproj --project-name test --version '0.2.0'
```

That's it. When done, you will have a new project directory, and in it, a `pyproject.toml` file containing dependencies from the entire Conda environment, dumped for your enjoyment.
