import argparse
import os
import time
import logging

from gensim.models import FastText
from nltk import RegexpTokenizer

_tokenizer = RegexpTokenizer("[\w]+|[^\w\s]|[0-9]+")
default_tokenizer = lambda text: _tokenizer.tokenize(text)


class Corpus(object):
    def __init__(self, fname, tokenizer=None):
        self.dirname = fname
        self.tok = default_tokenizer if tokenizer is None else tokenizer

    def __iter__(self):
        line_buf = ""
        ind = 0
        max_lines = 10
        for line in open(self.dirname):
            if ind < max_lines:
                line_buf += "\n" + line.lower()
                ind += 1
            else:
                tokens = self.tok(line_buf)
                yield tokens
                ind = 0
                line_buf = ""
        if line_buf:
            yield self.tok(line_buf)


# logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)

def train_fasttext(corpus_path, output_path, tokenizer=None):

    sentences = Corpus(corpus_path, tokenizer=tokenizer)

    logging.basicConfig(format='%(asctime)s : %(message)s', level=logging.INFO)

    print("FastText training started, ", time.strftime("%Y-%m-%d %H:%M"))
    model = FastText(sentences,
                     size=100,
                     window=15,
                     min_count=1,
                     workers=4,
                     sg=1,
                     negative=15,
                     ns_exponent=0.75,
                     sample=1e-4,
                     iter=20,
                     alpha=0.1,
                     min_alpha=5e-3,
                     sorted_vocab=1,
                     max_vocab_size=2000000,
                     word_ngrams=1,
                     bucket=200000,
                     min_n=3,
                     max_n=5)

    print("FastText training finished, ", time.strftime("%Y-%m-%d %H:%M"))

    if not os.path.isdir(output_path):
        os.mkdir(output_path)

    model.wv.save_word2vec_format(output_path + "/" + 'emb.txt')
    print("Embeddings saved, ", time.strftime("%Y-%m-%d %H:%M"))
    model.save(output_path + "/" + 'model')
    print("Model saved, ", time.strftime("%Y-%m-%d %H:%M"))


def main():
    parser = argparse.ArgumentParser(description='Train word vectors')
    parser.add_argument('input_file', type=str, default=150, help='Path to text file')
    parser.add_argument('output_dir', type=str, default=5, help='Ouput saving directory')
    args = parser.parse_args()

    corpus_path = args.input_file
    output_path = args.output_dir

    train_fasttext(corpus_path, output_path)


if __name__ == "__main__":
    main()
