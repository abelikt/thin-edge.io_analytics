#!/usr/bin/python3
"""Download all thin-edge system-test artifacts from GitHub.

First get a list of all workflow runs.
Then filter out the system-test-workflows.
Retrieve the URL of the system-test-workflow artifact and download it.

In order to run, you need a GitHub token set to $THEGHTOKEN.
See https://github.com/settings/tokens to generate a token with repo, workflow scope.


See also here
https://docs.github.com/en/rest/reference/actions#download-an-artifact
"""

# Hint: Without the auth token we get this error message:
#
# {'message': "API rate limit exceeded. (But here's the good news:
# Authenticated requests get a higher rate limit. Check out the
# documentation for more details.)", 'documentation_url':
# 'https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting'}

# TODO: Add some heuristic to know if we have most of the data
# available and can skip downloading

import argparse
import json
import os
import sys
import requests
from requests.auth import HTTPBasicAuth


def download_artifact(url, name, run_number, token, lake, user, runner):
    """Download the artifact and store it as a zip file.
    Also repair the filename if the name is outdated"""

    headers = {"Accept": "application/vnd.github.v3+json"}

    auth = HTTPBasicAuth(user, token)

    print(f"Will try {lake}/{name}.zip aka results_{run_number}'")

    # Repair names from old test runs (many tries to the the name right)
    if runner == 'run analytics':
        #name = f"{runner}_results_{run_number}"
        name = f"run_analytics_results_{run_number}"
    elif name == "results_":
        name = f"results_{run_number}"
    elif name == "results_$RUN_NUMBER":
        name = f"results_{run_number}"
    elif name == "results":
        name = f"results_{run_number}"
    elif name == "results_$GITHUB_RUN_ID":
        name = f"results_{run_number}"
    else:
        assert name == f"results_{run_number}"

    artifact_filename = f"{lake}/{name}.zip"

    if os.path.exists(artifact_filename):
        print(f"Skipped {lake}/{name}.zip")
        return False

    req = requests.get(url, auth=auth, headers=headers, stream=True)

    with open(os.path.expanduser(artifact_filename), "wb") as thefile:
        for chunk in req.iter_content(chunk_size=128):

            if chunk.startswith(b'{"message"'):
                raise SystemError("Something went wrong: We just drop off now. GH says expired !!!", chunk)
                #raise SystemError("Something went wrong:", chunk)

            thefile.write(chunk)
        print(f"Downloaded {lake}/{name}.zip")

    return True


def get_artifacts_for_runid(runid, run_number, token, lake, user, runner):
    """Download artifacts for a given runid"""
    # Here we need the runid and we get the artifact id

    # manual example
    # https://github.com/abelikt/thin-edge.io/actions/runs/828065682
    # curl -H "Accept: application/vnd.github.v3+json" -u abelikt:$TOKEN
    # -L https://api.github.com/repos/abelikt/thin-edge.io/actions/runs/828065682/artifacts

    url = f"https://api.github.com/repos/{user}/thin-edge.io/actions/runs/{runid}/artifacts"
    headers = {"Accept": "application/vnd.github.v3+json"}

    auth = HTTPBasicAuth(user, token)

    req = requests.get(url, auth=auth, headers=headers)
    text = json.loads(req.text)

    with open(
        os.path.expanduser(f"{lake}/{runner}_results_{run_number}_metadata.json"), "w"
    ) as ofile:
        ofile.write(json.dumps(text, indent=4))

    artifacts = text["artifacts"]

    if len(artifacts) > 0:
        artifact_name = artifacts[0]["name"]
        artifact_url = artifacts[0]["archive_download_url"]
        print(artifact_url)
        ret = download_artifact(
            artifact_url, artifact_name, run_number, token, lake, user, runner
        )
        return ret
    else:
        print("No Artifact attached")

    return None


def get_all_runs(token, user):
    """Download all GitHub Actions workflow runs.
    Generator function that returns the next 100 runs from the web-ui
    as list of dictionaries.
    """

    # manual example
    # curl -H "Accept: application/vnd.github.v3+json" -u abelikt:$TOKEN
    # -L https://api.github.com/repos/abelikt/thin-edge.io/actions/runs

    url = f"https://api.github.com/repos/{user}/thin-edge.io/actions/runs"
    headers = {"Accept": "application/vnd.github.v3+json"}

    auth = HTTPBasicAuth("abelikt", token)

    index = 1  # Hint: 0 and 1 seem to have an identical meaning when we request
    empty = False

    while not empty:
        print(f"Request {index}")

        # larger values than 100 do not seem to have an effect
        params = {"per_page": "100", "page": index}
        req = requests.get(url, params=params, auth=auth, headers=headers)
        stuff = json.loads(req.text)

        try:
            read = len(stuff["workflow_runs"])
        except KeyError as kerror:
            print("Error", kerror, stuff)
            print("Error: Message from GitHub: ", stuff["message"])
            sys.exit(1)

        if read == 0:
            print("Empty")
            return {}
        else:
            print(f"Read {read} entries")

        index += 1
        yield stuff["workflow_runs"]


def get_all_system_test_runs(token, lake, user, runner):
    """Returns als system test runs as list of run_id and number"""

    system_test_runs = []
    for test_runs in get_all_runs(token, user):
        for test_run in test_runs:
            if test_run["name"] == runner:
                run_number = test_run["run_number"]
                with open(
                    os.path.expanduser(
                        f"{lake}/{runner}_system_test_{run_number}_metadata.json"
                    ),
                    "w",
                ) as ofile:
                    ofile.write(json.dumps(test_run, indent=4))
                print(
                    f"Found System Test Run {test_run['name']} with id {test_run['id']}"
                    f" run number {run_number} workflow id {test_run['workflow_id']}"
                )
                system_test_runs.append((test_run["id"], run_number))

                if run_number == 1:
                    # Multilevel break: Will hit for newer workflows with
                    # smaller run numbers
                    return system_test_runs
                    print(f"Found {len(system_test_runs)} test_runs")

    print(f"Found {len(system_test_runs)} test_runs")

    return system_test_runs


def main(lake, username):
    """main entry point"""
    token = None
    lake = os.path.expanduser(lake)

    if "THEGHTOKEN" in os.environ:
        token = os.environ["THEGHTOKEN"]
    else:
        print("Error environment variable THEGHTOKEN not set")
        sys.exit(1)

    #runner = "system-test-workflow":
    #runner = "ci_pipeline":
    runner = 'run analytics'

    print(f'Getting logs for runner {runner}')
    system_test_runs = get_all_system_test_runs(token, lake, username, runner)

    skip_counter = 0
    for run in system_test_runs:
        print("Processing system test with runid {run[0]} and run number {run[1]}")
        ret = get_artifacts_for_runid(run[0], run[1], token, lake, username, runner)
        if ret == False:
            skip_counter += 1

        if skip_counter > 20:
            print("Skipped already 20 times, lets hope we are done")
            return


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("username", type=str, help="GitHub Username")
    args = parser.parse_args()

    user = args.username
    lake = "~/DataLake"

    main(lake, user)
