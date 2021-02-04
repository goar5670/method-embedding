conda activate SourceCodeTools
python type_prediction.py --tokenizer /Users/LTV/Downloads/NitroShare/spacy-python-with-tok --data_path ~/data/datasets/source_code/graphs/python-source-graph/v2_subsample/with_ast/functions_with_annotations.jsonl --graph_emb_path ~/data/datasets/source_code/graphs/python-source-graph/v2_subsample/with_ast/for_dglke/RESCAL_u/RESCAL_code_0/embeddings.pkl --word_emb_path ~/dev/method-embedding/codesearchnet_100.pkl --learning_rate 0.001 --learning_rate_decay 0.999 --hyper_search ~/Documents/type-graph-rescal
python type_prediction.py --tokenizer /Users/LTV/Downloads/NitroShare/spacy-python-with-tok --data_path ~/data/datasets/source_code/graphs/python-source-graph/v2_subsample/with_ast/functions_with_annotations.jsonl --graph_emb_path ~/data/datasets/source_code/graphs/python-source-graph/v2_subsample/with_ast/for_dglke/RotatE_u/RotatE_code_0/embeddings.pkl --word_emb_path ~/dev/method-embedding/codesearchnet_100.pkl --learning_rate 0.001 --learning_rate_decay 0.999 --hyper_search ~/Documents/type-graph-rotate
python type_prediction.py --tokenizer /Users/LTV/Downloads/NitroShare/spacy-python-with-tok --data_path ~/data/datasets/source_code/graphs/python-source-graph/v2_subsample/with_ast/functions_with_annotations.jsonl --graph_emb_path ~/data/datasets/source_code/graphs/python-source-graph/v2_subsample/with_ast/for_dglke/transr_u/TransR_code_2/embeddings.pkl --word_emb_path ~/dev/method-embedding/codesearchnet_100.pkl --learning_rate 0.001 --learning_rate_decay 0.999 --hyper_search ~/Documents/type-graph-transr
conda deactivate
