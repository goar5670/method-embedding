import pandas as pd
import sys, os
from csv import QUOTE_NONNUMERIC

all_nodes = pd.read_csv(sys.argv[1])
orig_nodes = pd.read_csv(sys.argv[2])

input_path = sys.argv[3]
output_path = sys.argv[4]
columns = sys.argv[5:]


rev_id_map = dict(zip(all_nodes['serialized_name'].tolist(), all_nodes['id'].tolist()))
id_map = dict(zip(orig_nodes["id"].tolist(), map(lambda x: rev_id_map[x], orig_nodes["serialized_name"].tolist())))

input_table = pd.read_csv(input_path)

for col in columns:
    input_table[col] = input_table[col].apply(lambda x: id_map[x])

if os.path.isfile(output_path):
    col_order = pd.read_csv(output_path).columns
    input_table[col_order].to_csv(output_path, index=False, header=False, quoting=QUOTE_NONNUMERIC, mode="a")
else:
    input_table.to_csv(output_path, index=False, header=True, quoting=QUOTE_NONNUMERIC, mode="a")
