from distutils.core import setup

setup(name='SourceCodeTools',
      version='0.0.2',
      py_modules=['SourceCodeTools'],
      install_requires=[
            'nltk',
            'tensorflow==2.4.0',
            'pandas>=1.1.1',
            'sklearn',
            'sentencepiece',
            'gensim',
            'numpy',
            'scipy'
            # 'javac_parser'
      ],
      scripts=[
            'SourceCodeTools/data/sourcetrail/sourcetrail_call_seq_extractor.py',
            # 'SourceCodeTools/data/sourcetrail/compress_to_bz2.py',
            'SourceCodeTools/data/sourcetrail/deprecated/sourcetrail_edge_types_to_int.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_extract_node_names.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_extract_variable_names.py',
            'SourceCodeTools/data/sourcetrail/deprecated/sourcetrail_extract_type_information.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_filter_ambiguous_edges.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_compute_function_diameter.py',
            # 'SourceCodeTools/data/sourcetrail/filter_edges_by_type.py',
            # 'SourceCodeTools/data/sourcetrail/filter_packages.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_add_reverse_edges.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_ast_edges.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_merge_graphs.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_parse_bodies.py',
            # 'SourceCodeTools/data/sourcetraildeprecated/sourcetrail_extract_docstring.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_edges_name_resolve.py',
            # 'SourceCodeTools/data/sourcetrail/deprecated/sourcetrail_filter_edges.py',
            # 'SourceCodeTools/data/sourcetrail/deprecated/sourcetrail_graph_properties_spark.py',
            # 'SourceCodeTools/data/sourcetrail/deprecated/sourcetrail_names_to_packages.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_node_name_merge.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_decode_edge_types.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_verify_files.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_map_id_columns.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_map_id_columns_only_annotations.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_node_local2global.py',
            'SourceCodeTools/data/sourcetrail/sourcetrail_connected_component.py',
            'SourceCodeTools/data/sourcetrail/pandas_format_converter.py',
            'SourceCodeTools/proc/entity/annotator/sourcecodetools-extract-type-annotations.py',
            # 'SourceCodeTools/proc/entity/sourcecodetools-replace-tokenizer.py',
            # 'SourceCodeTools/proc/entity/sourcecodetools-spacy-ner.py',
            'SourceCodeTools/nlp/embed/converters/convert_fasttext_format_bin_to_vec.py',
      ],
)
