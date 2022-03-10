import sys

from SourceCodeTools.code.common import map_columns, merge_with_file_if_exists
from SourceCodeTools.code.data.ast_graph.local2global import create_local_to_global_id_map
from SourceCodeTools.code.data.file_utils import *


if __name__ == "__main__":
    global_nodes_path = sys.argv[1]
    local_nodes_path = sys.argv[2]
    input_path = sys.argv[3]
    output_path = sys.argv[4]
    columns = sys.argv[5:]

    global_nodes = unpersist_or_exit(global_nodes_path, exit_message = "Error: global nodes do not exist!")
    local_nodes = unpersist_or_exit(local_nodes_path)
    input_table = unpersist_or_exit(input_path)

    id_map = create_local_to_global_id_map(local_nodes=local_nodes, global_nodes=global_nodes)

    data = map_columns(input_table, id_map, columns)

    if data is not None:
        data = merge_with_file_if_exists(df=input_table, merge_with_file=output_path)
        persist(data, output_path)
