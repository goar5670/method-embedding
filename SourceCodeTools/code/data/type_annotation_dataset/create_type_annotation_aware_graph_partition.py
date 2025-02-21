import argparse
import json
from os.path import join
from random import random

import pandas as pd

from SourceCodeTools.code.common import read_nodes
from SourceCodeTools.code.data.file_utils import persist


def add_splits(items, train_frac, restricted_id_pool=None, force_test=None):
    items = items.copy()

    if force_test is None:
        force_test = set()

    def random_partition(node_id):
        r = random()
        if node_id not in force_test:
            if r < train_frac:
                return "train"
            elif r < train_frac + (1 - train_frac) / 2:
                return "val"
            else:
                return "test"
        else:
            if r < .5:
                return "val"
            else:
                return "test"

    import numpy as np
    # define partitioning
    masks = np.array([random_partition(node_id) for node_id in items["id"]])

    # create masks
    items["train_mask"] = masks == "train"
    items["val_mask"] = masks == "val"
    items["test_mask"] = masks == "test"

    if restricted_id_pool is not None:
        # if `restricted_id_pool` is provided, mask all nodes not in `restricted_id_pool` negatively
        to_keep = items.eval("id in @restricted_ids", local_dict={"restricted_ids": restricted_id_pool})
        items["train_mask"] = items["train_mask"] & to_keep
        items["test_mask"] = items["test_mask"] & to_keep
        items["val_mask"] = items["val_mask"] & to_keep

    return items


def read_test_set_nodes(path):
    node_ids = set()
    with open(path, "r") as dataset:
        for line in dataset:
            if line.strip() == "":
                continue

            text, entry = json.loads(line)

            for _, _, node_id in entry["replacements"]:
                node_ids.add(node_id)

    return node_ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("working_directory")
    parser.add_argument("type_annotation_test_set")
    parser.add_argument("output_path")

    args = parser.parse_args()

    all_nodes = []
    for nodes in read_nodes(join(args.working_directory, "common_nodes.json.bz2"), as_chunks=True):
        all_nodes.append(nodes[["id"]])

    partition = add_splits(
        items=pd.concat(all_nodes),
        train_frac=0.8,
        force_test=read_test_set_nodes(args.type_annotation_test_set)
    )

    persist(partition, args.output_path)




if __name__ == "__main__":
    main()