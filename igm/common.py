#!/usr/bin/env python3

"""
Copyright (C) 2021-2023 Guillaume Jouvet <guillaume.jouvet@unil.ch>
Published under the GNU GPL (Version 3), check at the LICENSE file
"""

import os, json
from json import JSONDecodeError
import importlib
import argparse
from igm.modules.utils import str2bool
import igm
import logging

from pathlib import Path
from functools import partial
from typing import List, Any, Dict


class State:
    pass


# this create core parameters for any IGM run
def params_core():
    parser = argparse.ArgumentParser(description="IGM")

    parser.add_argument(
        "--working_dir",
        type=str,
        default="",
        help="Working directory (default empty string)",
    )
    parser.add_argument(
        "--param_file",
        type=str,
        default="params.json",
        help="Path for the JSON parameter file.",
    )
    parser.add_argument(
        "--modules_preproc",
        type=list,
        default=["oggm_shop"],
        help="List of pre-processing modules",
    )
    parser.add_argument(
        "--modules_process",
        type=list,
        default=["iceflow", "time", "thk"],
        help="List of processing modules",
    )
    parser.add_argument(
        "--modules_postproc",
        type=list,
        default=["write_ncdf", "plot2d", "print_info"],
        help="List of post-processing modules",
    )
    parser.add_argument(
        "--logging",
        type=str2bool,
        default=False,
        help="Activate the logging",
    )
    parser.add_argument(
        "--logging_file",
        type=str,
        default="",
        help="Logging file name, if empty it prints in the screen",
    )
    parser.add_argument(
        "--print_params",
        type=str,
        default=True,
        help="Print definitive parameters in a file for record",
    )
    parser.add_argument(
        "--gpu",
        type=int,
        default=0,
        help="Id of the GPU to use (default 0)",
    )
    return parser


# Function to remove comments from a JSON string
def remove_comments(json_str):
    lines = json_str.split("\n")
    cleaned_lines = [line for line in lines if not line.strip().startswith(("//", "#"))] # ! TODO: Add blocks comments...
    return "\n".join(cleaned_lines)


def get_modules_list(params_path: str):
    try:
        with open(params_path) as f:
            # params_dict = json.load(f) #re-instate if you want to enforce no comments in the json file
            json_text = f.read()
            json_cleaned = remove_comments(json_text)
            params_dict = json.loads(json_cleaned)
            module_dict = {
                "modules_preproc": params_dict["modules_preproc"],
                "modules_process": params_dict["modules_process"],
                "modules_postproc": params_dict["modules_postproc"],
            }

            return module_dict
    except JSONDecodeError as e:
        raise JSONDecodeError(
            msg="For the following line, please check the 1) JSON file structure and/or 2) make sure there are no comments (//, #, etc.)",
            doc=e.doc,
            pos=e.pos,
        )


def overide_from_json_file(parser, check_if_params_exist=True):
    # get the path of the json file
    param_file = os.path.join(parser.parse_args(args=[]).working_dir, "params.json")

    # load the given parameters from the json file
    with open(param_file, "r") as json_file:
        json_text = json_file.read()

    # Remove comments from the JSON string
    json_without_comments = remove_comments(json_text)

    # Parse the modified JSON string
    try:
        dic_params = json.loads(json_without_comments)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")

    # list only the parameters registered so far
    LIST = list(vars(parser.parse_args(args=[])).keys())

    if "time_step" in dic_params["modules_process"]:
        import sys

        print(
            " ------- CHECK THE WIKI TO CHANGE YOUR PARAM FILE AND USER MODULES -------------"
        )
        sys.exit(
            "WARNING: the parameter time_step is deprecated, UPDATE you params.json file"
        )

    if check_if_params_exist:
        for key in dic_params.keys():
            if not key in LIST:
                print(
                    "WARNING: the following parameters of the json file do not exist in igm: ",
                    key,
                )

    # keep only the parameters to overide hat were registerd so far
    filtered_dict = {key: value for key, value in dic_params.items() if key in LIST}

    parser.set_defaults(**filtered_dict)


def load_modules(modules_dict: Dict) -> List:
    """Returns a list of actionable modules to then apply the update, initialize, finalize functions on for IGM."""

    imported_preproc_modules = load_modules_from_directory(
        modules_list=modules_dict["modules_preproc"], module_folder="preproc"
    )
    imported_process_modules = load_modules_from_directory(
        modules_list=modules_dict["modules_process"], module_folder="process"
    )
    imported_postproc_modules = load_modules_from_directory(
        modules_list=modules_dict["modules_postproc"], module_folder="postproc"
    )
    # ? Should we have custom modules in a seperate folder?
    # imported_custom_modules = load_modules_from_directory(
    #     modules_list=modules_dict.modules_custom, module_folder=params.modules_custom_folder
    # )

    return (
        imported_preproc_modules
        + imported_process_modules
        + imported_postproc_modules  # + imported_custom_modules
    )


def validate_module(module) -> None:
    """Validates that a module has the required functions to be used in IGM."""
    required_functions = ["params", "initialize", "finalize", "update"]
    for function in required_functions:
        if not hasattr(module, function):
            raise AttributeError(
                f"Module {module} is missing the required function ({function}). If it is a custom python package, make sure to include it in the __init__.py file.",
                f"Please see https://github.com/jouvetg/igm/wiki/5.-Custom-modules-(coding) for more information on how to construct custom modules.",
            )


def load_modules_from_directory(
    modules_list: List[str], module_folder: str
) -> List[Any]:
    imported_modules = []

    for module_name in modules_list:
        module_path = f"igm.modules.{module_folder}.{module_name}"
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError:
            logging.info(
                f"Error importing module: {module_path}, checking for custom package in current working directory."
            )
            try:
                logging.info(
                    f"Trying to import custom module from current working directory (folder or .py): {module_name}"
                )
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                raise ModuleNotFoundError(
                    f"Can not find module {module_name}. Make sure it is either in the 1) {Path(igm.__file__).parent}/modules/{module_folder} directory or 2) in your current working directory."
                )

        validate_module(module)
        imported_modules.append(module)

    return imported_modules


def has_dependencies(module: Any):
    if hasattr(module, "dependencies"):
        return True


# ! TODO: Make this function better apdated to dependencies, modulenames, and paths... (for custom and inbuilt)
def add_dependencies(imported_modules: List):
    imported_dependencies = set()
    for module in imported_modules:
        if has_dependencies(module):
            module_dependencies = module.dependencies
            directories_to_search = [
                "preproc",
                "process",
                "postproc",
            ]  # will also check current working directory if any of them fail
            load_modules_partial = partial(
                load_modules_from_directory, module_dependencies
            )
            for directory in directories_to_search:
                try:
                    dependent_module = load_modules_partial(module_folder=directory)
                    imported_dependencies.add(dependent_module[0]) #[0] because it returns a singleton list
                    logging.info(
                        f"Found dependencies in directory {directory} or current working directory. Checking next module for dependencies."
                    )
                    break
                except ModuleNotFoundError:
                    logging.info(
                        f"Could not find dependencies in directory {directory} or current working directory. Checking next IGM directory."
                    )

    return imported_modules + list(imported_dependencies)


# this add a logger to the state
def add_logger(params, state, logging_level="INFO"):
    import logging

    if params.logging_file == "":
        pathf = ""
    else:
        pathf = os.path.join(params.working_dir, params.logging_file)

    logging.basicConfig(
        filename=pathf,
        encoding="utf-8",
        filemode="w",
        level=getattr(logging, logging_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    state.logger = logging.getLogger("my_logger")

    if not pathf == "":
        os.system("echo rm " + pathf + " >> clean.sh")


# Print parameters in screen and a dedicated file
def print_params(params):
    param_file = os.path.join(params.working_dir, "params_saved.json")

    # load the given parameters
    with open(param_file, "w") as json_file:
        json.dump(params.__dict__, json_file, indent=2)

    os.system("echo rm " + param_file + " >> clean.sh")
