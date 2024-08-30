# coding=utf-8
# Copyright 2022 The HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import copy
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import glob
import yaml


COMMON_ENV_VARIABLES = {
    "OMP_NUM_THREADS": 1,
    "TRANSFORMERS_IS_CI": True,
    "PYTEST_TIMEOUT": 120,
    "RUN_PIPELINE_TESTS": False,
    "RUN_PT_TF_CROSS_TESTS": False,
    "RUN_PT_FLAX_CROSS_TESTS": False,
}
# Disable the use of {"s": None} as the output is way too long, causing the navigation on CircleCI impractical
COMMON_PYTEST_OPTIONS = {"max-worker-restart": 0, "dist": "loadfile", "vvv": None, "rsf":None}
DEFAULT_DOCKER_IMAGE = [{"image": "cimg/python:3.8.12"}]


class EmptyJob:
    job_name = "empty"

    def to_dict(self):
        return {
            "docker": copy.deepcopy(DEFAULT_DOCKER_IMAGE),
            "steps":["checkout"],
        }


@dataclass
class CircleCIJob:
    name: str
    additional_env: Dict[str, Any] = None
    docker_image: List[Dict[str, str]] = None
    install_steps: List[str] = None
    marker: Optional[str] = None
    parallelism: Optional[int] = 0
    pytest_num_workers: int = 12
    pytest_options: Dict[str, Any] = None
    resource_class: Optional[str] = "2xlarge"
    tests_to_run: Optional[List[str]] = None
    num_test_files_per_worker: Optional[int] = 10
    # This should be only used for doctest job!
    command_timeout: Optional[int] = None

    def __post_init__(self):
        # Deal with defaults for mutable attributes.
        if self.additional_env is None:
            self.additional_env = {}
        if self.docker_image is None:
            # Let's avoid changing the default list and make a copy.
            self.docker_image = copy.deepcopy(DEFAULT_DOCKER_IMAGE)
        else:
            # BIG HACK WILL REMOVE ONCE FETCHER IS UPDATED
            print(os.environ.get("GIT_COMMIT_MESSAGE"))
            if "[build-ci-image]" in os.environ.get("GIT_COMMIT_MESSAGE", "") or os.environ.get("GIT_COMMIT_MESSAGE", "") == "dev-ci":
                self.docker_image[0]["image"] = f"{self.docker_image[0]['image']}:dev"
            print(f"Using {self.docker_image} docker image")
        if self.install_steps is None:
            self.install_steps = ["uv venv && uv pip install ."]
        if self.pytest_options is None:
            self.pytest_options = {}
        if isinstance(self.tests_to_run, str):
            self.tests_to_run = [self.tests_to_run]
        else:
            test_file = os.path.join("test_preparation" , f"{self.job_name}_test_list.txt")
            print("Looking for ", test_file)
            if os.path.exists(test_file):
                with open(test_file) as f:
                    expanded_tests = f.read().strip().split("\n")
                self.tests_to_run = expanded_tests
                print("Found:", expanded_tests)
            else:
                self.tests_to_run = []
                print("not Found")

    def to_dict(self):
        env = COMMON_ENV_VARIABLES.copy()
        env.update(self.additional_env)

        job = {
            "docker": self.docker_image,
            "environment": env,
        }
        if self.resource_class is not None:
            job["resource_class"] = self.resource_class

        all_options = {**COMMON_PYTEST_OPTIONS, **self.pytest_options}
        pytest_flags = [f"--{key}={value}" if (value is not None or key in ["doctest-modules"]) else f"-{key}" for key, value in all_options.items()]
        pytest_flags.append(
            f"--make-reports={self.name}" if "examples" in self.name else f"--make-reports=tests_{self.name}"
        )
                # Examples special case: we need to download NLTK files in advance to avoid cuncurrency issues
        timeout_cmd = f"timeout {self.command_timeout} " if self.command_timeout else ""
        marker_cmd = f"-m '{self.marker}'" if self.marker is not None else ""
        additional_flags = f" -p no:warning -o junit_family=xunit1 --junitxml=test-results/junit.xml"
        steps = [
            "checkout",
            {"attach_workspace": {"at": "test_preparation"}},
            {"run": "apt-get update && apt-get install -y curl"},
            {"run": " && ".join(self.install_steps)},
            {"run": {"name": "Download NLTK files", "command": """python -c "import nltk; nltk.download('punkt', quiet=True)" """} if "example" in self.name else "echo Skipping"},
            {"run": {
                    "name": "Show installed libraries and their size",
                    "command": """du -h -d 1 "$(pip -V | cut -d ' ' -f 4 | sed 's/pip//g')" | grep -vE "dist-info|_distutils_hack|__pycache__" | sort -h | tee installed.txt || true"""}
            },
            {"run": {
                "name": "Show installed libraries and their versions",
                "command": """pip list --format=freeze | tee installed.txt || true"""}
            },
            {"run": {
                "name": "Show biggest libraries",
                "command": """dpkg-query --show --showformat='${Installed-Size}\t${Package}\n' | sort -rh | head -25 | sort -h | awk '{ package=$2; sub(".*/", "", package); printf("%.5f GB %s\n", $1/1024/1024, package)}' || true"""}
            },
            {"run": {"name": "Create `test-results` directory", "command": "mkdir test-results"}},
            {"run": {"name": "Get files to test", "command":f'curl -L -o {self.job_name}_test_list.txt <<pipeline.parameters.{self.job_name}_test_list>>' if self.name != "pr_documentation_tests" else 'echo "Skipped"'}},
            {"run": {"name": "Split tests across parallel nodes: show current parallel tests",
                    "command": f"TESTS=$(circleci tests split  --split-by=timings {self.job_name}_test_list.txt) && echo $TESTS > splitted_tests.txt && echo $TESTS | tr ' ' '\n'" if self.parallelism else f"awk '{{printf \"%s \", $0}}' {self.job_name}_test_list.txt > splitted_tests.txt"
                    }
            },
            {"run": {
                "name": "Run tests",
                "command": f"({timeout_cmd} python3 -m pytest {marker_cmd} -n {self.pytest_num_workers} {additional_flags} {' '.join(pytest_flags)} $(cat splitted_tests.txt) | tee tests_output.txt)"}
            },
            {"run": {"name": "Expand to show skipped tests", "when": "always", "command": f"python3 .circleci/parse_test_outputs.py --file tests_output.txt --skip"}},
            {"run": {"name": "Failed tests: show reasons",   "when": "always", "command": f"python3 .circleci/parse_test_outputs.py --file tests_output.txt --fail"}},
            {"run": {"name": "Errors",                       "when": "always", "command": f"python3 .circleci/parse_test_outputs.py --file tests_output.txt --errors"}},
            {"store_test_results": {"path": "test-results"}},
            {"store_artifacts": {"path": "test-results/junit.xml"}},
            {"store_artifacts": {"path": "reports"}},
            {"store_artifacts": {"path": "tests.txt"}},
            {"store_artifacts": {"path": "splitted_tests.txt"}},
            {"store_artifacts": {"path": "installed.txt"}},
        ]
        if self.parallelism:
            job["parallelism"] = self.parallelism
        job["steps"] = steps
        return job

    @property
    def job_name(self):
        return self.name if ("examples" in self.name or "pipeline" in self.name or "pr_documentation" in self.name) else f"tests_{self.name}"


# JOBS
torch_and_tf_job = CircleCIJob(
    "torch_and_tf",
    docker_image=[{"image":"huggingface/transformers-torch-tf-light"}],
    additional_env={"RUN_PT_TF_CROSS_TESTS": True},
    marker="is_pt_tf_cross_test",
    pytest_options={"rA": None, "durations": 0},
)


torch_and_flax_job = CircleCIJob(
    "torch_and_flax",
    additional_env={"RUN_PT_FLAX_CROSS_TESTS": True},
    docker_image=[{"image":"huggingface/transformers-torch-jax-light"}],
    marker="is_pt_flax_cross_test",
    pytest_options={"rA": None, "durations": 0},
)

torch_job = CircleCIJob(
    "torch",
    docker_image=[{"image": "huggingface/transformers-torch-light"}],
    marker="not generate",
    parallelism=6,
    pytest_num_workers=8
)

generate_job = CircleCIJob(
    "generate",
    docker_image=[{"image": "huggingface/transformers-torch-light"}],
    marker="generate",
    parallelism=6,
    pytest_num_workers=8
)

tokenization_job = CircleCIJob(
    "tokenization",
    docker_image=[{"image": "huggingface/transformers-torch-light"}],
    parallelism=8,
    pytest_num_workers=16
)

processor_job = CircleCIJob(
    "processors",
    docker_image=[{"image": "huggingface/transformers-torch-light"}],
    parallelism=8,
    pytest_num_workers=6
)

tf_job = CircleCIJob(
    "tf",
    docker_image=[{"image":"huggingface/transformers-tf-light"}],
    parallelism=6,
    pytest_num_workers=16,
)


flax_job = CircleCIJob(
    "flax",
    docker_image=[{"image":"huggingface/transformers-jax-light"}],
    parallelism=6,
    pytest_num_workers=16
)


pipelines_torch_job = CircleCIJob(
    "pipelines_torch",
    additional_env={"RUN_PIPELINE_TESTS": True},
    docker_image=[{"image":"huggingface/transformers-torch-light"}],
    marker="is_pipeline_test",
    parallelism=4
)


pipelines_tf_job = CircleCIJob(
    "pipelines_tf",
    additional_env={"RUN_PIPELINE_TESTS": True},
    docker_image=[{"image":"huggingface/transformers-tf-light"}],
    marker="is_pipeline_test",
    parallelism=4
)


custom_tokenizers_job = CircleCIJob(
    "custom_tokenizers",
    additional_env={"RUN_CUSTOM_TOKENIZERS": True},
    docker_image=[{"image": "huggingface/transformers-custom-tokenizers"}],
)


examples_torch_job = CircleCIJob(
    "examples_torch",
    additional_env={"OMP_NUM_THREADS": 8},
    docker_image=[{"image":"huggingface/transformers-examples-torch"}],
    # TODO @ArthurZucker remove this once docker is easier to build
    install_steps=["uv venv && uv pip install . && uv pip install -r examples/pytorch/_tests_requirements.txt"],
    pytest_num_workers=8,
)


examples_tensorflow_job = CircleCIJob(
    "examples_tensorflow",
    additional_env={"OMP_NUM_THREADS": 8},
    docker_image=[{"image":"huggingface/transformers-examples-tf"}],
    pytest_num_workers=16,
)


hub_job = CircleCIJob(
    "hub",
    additional_env={"HUGGINGFACE_CO_STAGING": True},
    docker_image=[{"image":"huggingface/transformers-torch-light"}],
    install_steps=[
        'uv venv && uv pip install .',
        'git config --global user.email "ci@dummy.com"',
        'git config --global user.name "ci"',
    ],
    marker="is_staging_test",
    pytest_num_workers=2,
)


onnx_job = CircleCIJob(
    "onnx",
    docker_image=[{"image":"huggingface/transformers-torch-tf-light"}],
    install_steps=[
        "uv venv",
        "uv pip install .[torch,tf,testing,sentencepiece,onnxruntime,vision,rjieba]",
    ],
    pytest_options={"k onnx": None},
    pytest_num_workers=1,
)


exotic_models_job = CircleCIJob(
    "exotic_models",
    docker_image=[{"image":"huggingface/transformers-exotic-models"}],
    pytest_num_workers=12,
    parallelism=4,
    pytest_options={"durations": 100},
)


repo_utils_job = CircleCIJob(
    "repo_utils",
    docker_image=[{"image":"huggingface/transformers-consistency"}],
    pytest_num_workers=4,
    resource_class="large",
)


# We also include a `dummy.py` file in the files to be doc-tested to prevent edge case failure. Otherwise, the pytest
# hangs forever during test collection while showing `collecting 0 items / 21 errors`. (To see this, we have to remove
# the bash output redirection.)
py_command = 'from utils.tests_fetcher import get_doctest_files; to_test = get_doctest_files() + ["dummy.py"]; to_test = " ".join(to_test); print(to_test)'
py_command = f"$(python3 -c '{py_command}')"
command = f'echo """{py_command}""" > pr_documentation_tests_temp.txt'
doc_test_job = CircleCIJob(
    "pr_documentation_tests",
    docker_image=[{"image":"huggingface/transformers-consistency"}],
    additional_env={"TRANSFORMERS_VERBOSITY": "error", "DATASETS_VERBOSITY": "error", "SKIP_CUDA_DOCTEST": "1"},
    install_steps=[
        # Add an empty file to keep the test step running correctly even no file is selected to be tested.
        "uv venv && pip install .",
        "touch dummy.py",
        command,
        "cat pr_documentation_tests_temp.txt",
        "tail -n1 pr_documentation_tests_temp.txt | tee pr_documentation_tests_test_list.txt"
    ],
    tests_to_run="$(cat pr_documentation_tests.txt)",  # noqa
    pytest_options={"-doctest-modules": None, "doctest-glob": "*.md", "dist": "loadfile", "rvsA": None},
    command_timeout=1200,  # test cannot run longer than 1200 seconds
    pytest_num_workers=1,
)

REGULAR_TESTS = [torch_and_tf_job, torch_and_flax_job, torch_job, tf_job, flax_job, hub_job, onnx_job, tokenization_job, processor_job, generate_job] # fmt: skip
EXAMPLES_TESTS = [examples_torch_job, examples_tensorflow_job]
PIPELINE_TESTS = [pipelines_torch_job, pipelines_tf_job]
REPO_UTIL_TESTS = [repo_utils_job]
DOC_TESTS = [doc_test_job]
ALL_TESTS = REGULAR_TESTS + EXAMPLES_TESTS + PIPELINE_TESTS + REPO_UTIL_TESTS + DOC_TESTS + [custom_tokenizers_job] + [exotic_models_job]  # fmt: skip

def create_circleci_config(folder=None):
    if folder is None:
        folder = os.getcwd()
    os.environ["test_preparation_dir"] = folder
    jobs = [k for k in ALL_TESTS if len(k.tests_to_run) > 0]
    print("The following jobs will be run ", jobs)

    if len(jobs) == 0:
        jobs = [EmptyJob()]
    print("Full list of job name inputs", {j.job_name + "_test_list":{"type":"string", "default":''} for j in jobs})
    config = {
        "version": "2.1",
        "parameters": {
            # Only used to accept the parameters from the trigger
            "nightly": {"type": "boolean", "default": False},
            "tests_to_run": {"type": "string", "default": ''},
            **{j.job_name + "_test_list":{"type":"string", "default":''} for j in ALL_TESTS},
        },
        "jobs" : {j.job_name: j.to_dict() for j in jobs},
        "workflows": {"version": 2, "run_tests": {"jobs": [j.job_name for j in jobs]}}
    }
    with open(os.path.join(folder, "generated_config.yml"), "w") as f:
        f.write(yaml.dump(config, indent=2, width=1000000, sort_keys=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fetcher_folder", type=str, default=None, help="Only test that all tests and modules are accounted for."
    )
    args = parser.parse_args()

    create_circleci_config(args.fetcher_folder)
