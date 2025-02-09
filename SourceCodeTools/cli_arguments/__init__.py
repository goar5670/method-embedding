import argparse


class AstDatasetCreatorArguments:
    parser = None

    def __init__(self):
        parser = argparse.ArgumentParser(description='Merge indexed environments into a single graph')
        parser.add_argument('--language', "-l", dest="language", default="python", help='')
        parser.add_argument('--bpe_tokenizer', '-bpe', dest='bpe_tokenizer', type=str, help='')
        parser.add_argument('--create_subword_instances', action='store_true', default=False, help="")
        parser.add_argument('--connect_subwords', action='store_true', default=False,
                            help="Takes effect only when `create_subword_instances` is False")
        parser.add_argument('--only_with_annotations', action='store_true', default=False, help="")
        parser.add_argument('--do_extraction', action='store_true', default=False, help="")
        parser.add_argument('--visualize', action='store_true', default=False, help="")
        parser.add_argument('--track_offsets', action='store_true', default=False, help="")
        parser.add_argument('--recompute_l2g', action='store_true', default=False, help="")
        parser.add_argument('--remove_type_annotations', action='store_true', default=False, help="")
        parser.add_argument('--seed', type=int, default=None, help="")

        self.parser = parser
        self.add_positional_argument()
        self.additional_arguments()

    def add_positional_argument(self):
        self.parser.add_argument(
            'source_code', help='Path to DataFrame csv.'
        )
        self.parser.add_argument('output_directory', help='')

    def additional_arguments(self):
        self.parser.add_argument('--chunksize', default=10000, type=int, help='Chunksize for preparing dataset. Larger chunks are faster to process, but they take more memory.')
        self.parser.add_argument('--keep_frac', default=1.0, type=float, help="Fraction of the dataset to keep")

    def parse(self):
        return self.parser.parse_args()


class DatasetCreatorArguments(AstDatasetCreatorArguments):

    def add_positional_argument(self):
        self.parser.add_argument('indexed_environments', help='Path to environments indexed by sourcetrail')
        self.parser.add_argument('output_directory', help='')

    def additional_arguments(self):
        pass






