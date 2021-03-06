import sys
import os
import logging
import time
import json
import fcntl
import subprocess

import utils

logger = utils.configure_logging()
logger.info("Incoming")

configuration = utils.configuration
instances = utils.instances

def update_mirrors(commit_sha1):
    try:
        object_type = subprocess.check_output(
            ["git", "cat-file", "-t", commit_sha1],
            stderr=subprocess.STDOUT, cwd=configuration["critic.git"])
    except subprocess.CalledProcessError:
        logger.debug("Updating: critic.git")
        subprocess.check_output(
            ["git", "fetch", "--all", "--quiet"],
            stderr=subprocess.STDOUT, cwd=configuration["critic.git"])

        if "v8-jsshell.git" in configuration:
            logger.debug("Updating: v8-jsshell.git")
            subprocess.check_output(
                ["git", "fetch", "--all", "--quiet"],
                stderr=subprocess.STDOUT, cwd=configuration["v8-jsshell.git"])

        if "v8.git" in configuration:
            logger.debug("Updating: v8.git")
            subprocess.check_output(
                ["git", "fetch", "--all", "--quiet"],
                stderr=subprocess.STDOUT, cwd=configuration["v8.git"])

        logger.info("Updated mirrors")

        try:
            object_type = subprocess.check_output(
                ["git", "cat-file", "-t", commit_sha1],
                stderr=subprocess.STDOUT, cwd=configuration["critic.git"])
        except subprocess.CalledProcessError:
            logger.error("Commit not found: %s" % commit_sha1)
            return False

    if object_type.strip() != "commit":
        logger.error("Object is not a commit: %s" % commit_sha1)
        return False
    return True

critic = utils.Critic()

incoming_dir = os.path.join(configuration["queue-dir"], "incoming")
outgoing_dir = os.path.join(configuration["queue-dir"], "outgoing")

try:
    print_nothing_to_do = True
    custom_sha1s = set()

    while True:
        result = critic.operation(
            "CriticTester/list",
            data={ "instances": [instance["identifier"]
                                 for instance in instances] })

        if result["tests"]:
            print_nothing_to_do = True
            with utils.locked_directory(configuration["queue-dir"]):
                filenames = (set([filename for filename in os.listdir(incoming_dir)
                                  if filename.endswith(".json")]) |
                             set([filename for filename in os.listdir(outgoing_dir)
                                  if filename.endswith(".json")]))

                filenames -= set(["custom.json"])

                for review_id in result["tests"]:
                    for test in result["tests"][review_id]:
                        filename = "%s.json" % test["key"]
                        if filename in filenames:
                            filenames.remove(filename)
                            continue
                        if update_mirrors(test["commit"]):
                            incoming_filename = os.path.join(incoming_dir, filename)
                            with open(incoming_filename, "w") as incoming_file:
                                json.dump(test, incoming_file)
                            logger.debug("Created: %s" % filename)

                for filename in filenames:
                    incoming_filename = os.path.join(incoming_dir, filename)
                    if os.path.isfile(incoming_filename):
                        os.unlink(incoming_filename)
                        logger.debug("Deleted: %s" % filename)
        elif print_nothing_to_do:
            print_nothing_to_do = False
            logger.debug("No pending tests")

        if result["custom"]:
            with utils.locked_directory(configuration["queue-dir"]):
                custom_filename = os.path.join(incoming_dir, "custom.json")
                with open(custom_filename, "w") as custom_file:
                    json.dump(result["custom"], custom_file)

                custom_sha1 = result["custom"]["sha1"]
                if custom_sha1 and custom_sha1 not in custom_sha1s:
                    logger.debug("New custom SHA-1: " + custom_sha1)
                    update_mirrors(custom_sha1)
                    custom_sha1s.add(custom_sha1)

        time.sleep(10)
except KeyboardInterrupt:
    pass
